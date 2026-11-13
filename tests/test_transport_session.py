"""Adversarial invariants for the Issue #9 transport/session boundary."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from research.forward_validation import ForwardEvidenceStore
from research.transport_session import (
    DERIV_PUBLIC_WS,
    _validate_deriv_endpoint,
    TransportSessionRecord,
    assert_no_evidence_credit,
    build_deriv_public_session,
)


class TransportSessionTests(unittest.TestCase):
    def test_endpoint_is_exactly_pinned(self):
        self.assertEqual(_validate_deriv_endpoint(DERIV_PUBLIC_WS), DERIV_PUBLIC_WS)
        for endpoint in (
            "wss://evil.example/trading/v1/options/ws/public",
            "wss://api.derivws.com.evil.example/trading/v1/options/ws/public",
            "https://api.derivws.com/trading/v1/options/ws/public",
            "wss://user@api.derivws.com/trading/v1/options/ws/public",
            "wss://api.derivws.com/trading/v1/options/ws/public?x=1",
            "wss://api.derivws.com/other",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                _validate_deriv_endpoint(endpoint)

    def test_builder_requires_real_tls_socket(self):
        with self.assertRaisesRegex(ValueError, "SSLSocket"):
            build_deriv_public_session(
                endpoint=DERIV_PUBLIC_WS,
                tls_socket=Mock(),
            )

    def test_builder_rejects_wrong_endpoint_before_socket_use(self):
        with self.assertRaisesRegex(ValueError, "exact approved"):
            build_deriv_public_session(
                endpoint="wss://evil.example/",
                tls_socket=Mock(),
            )

    def test_session_started_at_must_be_timezone_aware(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_deriv_public_session(
                endpoint=DERIV_PUBLIC_WS,
                tls_socket=Mock(),
                started_at=datetime(2026, 11, 13, 12, 0, 0),
            )

    def test_session_json_copy_cannot_mutate_immutable_record(self):
        # This test asserts the record serializer's invariant. An altered JSON
        # copy is untrusted input and is not treated as a canonical record.
        record = TransportSessionRecord(
            session_id="session-test",
            endpoint=DERIV_PUBLIC_WS,
            provider="Deriv",
            started_at="2026-11-13T12:00:00+00:00",
            tls_socket_observed=True,
            peer_certificate_present=True,
            peer_certificate_sha256="abc",
            certificate_verification_mode="CERT_REQUIRED",
            hostname_check_enabled=True,
            collector_identity=None,
            notes="informational",
            evidence_credit=True,
        )
        with self.assertRaises(AssertionError):
            assert_no_evidence_credit(record)

    def test_store_still_blocks_provenance_with_forged_session_metadata(self):
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
        item = {
            "observed_at": now.isoformat(),
            "instrument": "EURUSD",
            "provider": "Deriv",
            "source": "deriv-public-wss-tick-v1",
            "interval": "tick",
            "strategy_id": "sma-crossover-long",
            "strategy_version": "1.0.0",
            "price": "1.08500",
            "transport_endpoint": DERIV_PUBLIC_WS,
            "transport_session_id": "forged-session",
            "transport_session": {
                "session_id": "forged-session",
                "endpoint": DERIV_PUBLIC_WS,
                "provider": "Deriv",
                "tls_socket_observed": True,
                "evidence_credit": False,
            },
            "provenance_verified": True,
        }
        self.assertTrue(store.ingest(item))
        report = store.report(1)
        self.assertEqual(report["verified_observation_count"], 0)
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
        self.assertFalse(report["level_3_certification"])
        self.assertFalse(report["provider_signature_or_equivalent_verifier_configured"])


if __name__ == "__main__":
    unittest.main()
