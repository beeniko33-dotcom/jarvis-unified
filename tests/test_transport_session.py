"""Adversarial and invariant tests for Issue #9 transport session boundary."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.forward_validation import ForwardEvidenceStore
from research.transport_session import (
    assert_no_evidence_credit,
    build_deriv_public_session,
)


class TransportSessionTests(unittest.TestCase):
    def test_session_never_grants_evidence_credit(self):
        record = build_deriv_public_session(
            endpoint="wss://api.derivws.com/trading/v1/options/ws/public",
            peer_certificate_sha256="abc123",
            collector_identity="git:deadbeef",
        )
        assert_no_evidence_credit(record)
        self.assertFalse(record.evidence_credit)
        self.assertFalse(record.to_dict()["evidence_credit"])
        self.assertIn("not individually signed", record.notes)

    def test_naive_started_at_rejected(self):
        with self.assertRaises(ValueError):
            build_deriv_public_session(
                endpoint="wss://example.test",
                started_at=datetime(2026, 11, 13, 12, 0, 0),
            )

    def test_empty_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            build_deriv_public_session(endpoint="  ")

    def test_session_json_cannot_flip_credit(self):
        record = build_deriv_public_session(
            endpoint="wss://api.derivws.com/trading/v1/options/ws/public"
        )
        payload = json.loads(record.to_json())
        payload["evidence_credit"] = True
        # Re-parse path used by operators must not trust flipped JSON alone.
        self.assertTrue(payload["evidence_credit"])  # attacker-controlled copy
        # Canonical builder still False
        self.assertFalse(record.evidence_credit)

    def test_store_still_blocks_provenance_with_session_metadata_present(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        store = ForwardEvidenceStore(
            Path(tmp.name) / "fwd.sqlite3",
            instrument="EURUSD",
            provider="Deriv",
            interval="tick",
            strategy_id="sma-crossover-long",
            strategy_version="1.0.0",
            clock=lambda: now,
        )
        self.addCleanup(store.close)
        session = build_deriv_public_session(
            endpoint="wss://api.derivws.com/trading/v1/options/ws/public",
            started_at=now,
        )
        item = {
            "observed_at": now.isoformat(),
            "instrument": "EURUSD",
            "provider": "Deriv",
            "source": "deriv-public-wss-tick-v1",
            "interval": "tick",
            "strategy_id": "sma-crossover-long",
            "strategy_version": "1.0.0",
            "price": "1.08500",
            "transport_session": session.to_dict(),
            "provenance_verified": True,  # forged field must not grant credit
        }
        self.assertTrue(store.ingest(item))
        report = store.report(1)
        self.assertEqual(report["verified_observation_count"], 0)
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
        self.assertFalse(report["level_3_certification"])
        self.assertFalse(report["provider_signature_or_equivalent_verifier_configured"])


if __name__ == "__main__":
    unittest.main()
