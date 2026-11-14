import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.deriv_feed import (
    DERIV_PUBLIC_WS, build_tick_observation, resolve_eurusd_symbol,
    validate_deriv_observation_binding,
)


class DerivFeedTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "session_id": "test-session-id",
            "endpoint": DERIV_PUBLIC_WS,
            "provider": "Deriv",
            "tls_socket_observed": True,
            "evidence_credit": False,
        }
        self.raw = json.dumps({
            "msg_type": "tick",
            "tick": {"symbol": "frxEURUSD", "epoch": 1794400000, "quote": 1.08525}
        }, separators=(",", ":"))
        self.item = build_tick_observation(
            self.raw, deriv_symbol="frxEURUSD",
            received_at=datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
            transport_session=self.session,
        )

    def test_resolves_eurusd_from_deriv_active_symbols(self):
        self.assertEqual(
            resolve_eurusd_symbol([
                {"symbol": "frxGBPUSD", "display_name": "GBP/USD"},
                {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
            ]),
            "frxEURUSD",
        )

    def test_resolves_eurusd_from_current_underlying_symbol_catalog(self):
        self.assertEqual(
            resolve_eurusd_symbol([
                {"underlying_symbol": "frxGBPUSD", "underlying_symbol_name": "GBP/USD"},
                {"underlying_symbol": "frxEURUSD", "underlying_symbol_name": "EUR/USD"},
            ]),
            "frxEURUSD",
        )

    def test_rejects_conflicting_symbol_fields(self):
        with self.assertRaisesRegex(ValueError, "conflicting symbol codes"):
            resolve_eurusd_symbol([
                {
                    "symbol": "frxEURUSD",
                    "underlying_symbol": "frxGBPUSD",
                    "display_name": "EUR/USD",
                }
            ])

    def test_rejects_missing_or_ambiguous_symbol(self):
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol([])
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol([
                {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                {"symbol": "EURUSD", "display_name": "EUR/USD"},
            ])

    def test_validates_payload_binding_without_claiming_transport_authenticity(self):
        self.assertTrue(validate_deriv_observation_binding(self.item))
        self.assertEqual(self.item["transport_endpoint"], DERIV_PUBLIC_WS)
        self.assertEqual(self.item["provider"], "Deriv")
        self.assertEqual(self.item["instrument"], "EURUSD")
        self.assertEqual(self.item["transport_security_claim"], "unverified")

    def test_caller_supplied_tls_claim_is_not_an_authenticator(self):
        item = dict(self.item, transport_security_claim="tls_verified")
        self.assertTrue(validate_deriv_observation_binding(item))
        epoch = 1794400000
        with tempfile.TemporaryDirectory() as directory:
            from research.forward_validation import ForwardEvidenceStore
            store = ForwardEvidenceStore(
                Path(directory) / "candidate.sqlite3",
                instrument="EURUSD", provider="Deriv", interval="tick",
                strategy_id="sma-crossover-long", strategy_version="1.0.0",
                clock=lambda: datetime.fromtimestamp(epoch + 1, timezone.utc),
            )
            try:
                store.ingest(item)
                report = store.report(1)
                self.assertEqual(report["verified_observation_count"], 0)
                self.assertEqual(report["unverified_candidate_count"], 1)
                self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
            finally:
                store.close()

    def test_rejects_session_id_mismatch(self):
        item = dict(self.item, transport_session_id="different-session")
        self.assertFalse(validate_deriv_observation_binding(item))

    def test_rejects_forged_session_credit(self):
        session = dict(self.session, evidence_credit=True)
        item = dict(self.item, transport_session=session)
        self.assertFalse(validate_deriv_observation_binding(item))

    def test_rejects_raw_payload_tampering(self):
        item = dict(self.item, raw_message=self.raw.replace("1.08525", "1.99999"))
        self.assertFalse(validate_deriv_observation_binding(item))

    def test_rejects_normalized_price_tampering(self):
        item = dict(self.item, price="1.99999")
        self.assertFalse(validate_deriv_observation_binding(item))

    def test_rejects_wrong_symbol(self):
        item = dict(self.item, deriv_symbol="frxGBPUSD")
        self.assertFalse(validate_deriv_observation_binding(item))

    def test_rejects_non_tick_payload(self):
        raw = json.dumps({"msg_type": "history", "tick": {"symbol": "frxEURUSD"}})
        with self.assertRaises(ValueError):
            build_tick_observation(
                raw, deriv_symbol="frxEURUSD",
                received_at=datetime.now(timezone.utc),
                transport_session=self.session,
            )


if __name__ == "__main__":
    unittest.main()
