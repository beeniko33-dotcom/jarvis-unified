import json
import unittest
from datetime import datetime, timezone

from research.deriv_feed import (
    DERIV_PUBLIC_WS, build_tick_observation, resolve_eurusd_symbol,
    verify_deriv_observation,
)


class DerivFeedTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.dumps({
            "msg_type": "tick",
            "tick": {"symbol": "frxEURUSD", "epoch": 1794400000, "quote": 1.08525}
        }, separators=(",", ":"))
        self.item = build_tick_observation(
            self.raw, deriv_symbol="frxEURUSD",
            received_at=datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
            tls_verified=True,
        )

    def test_resolves_eurusd_from_deriv_active_symbols(self):
        self.assertEqual(
            resolve_eurusd_symbol([
                {"symbol": "frxGBPUSD", "display_name": "GBP/USD"},
                {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
            ]),
            "frxEURUSD",
        )

    def test_rejects_missing_or_ambiguous_symbol(self):
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol([])
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol([
                {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                {"symbol": "EURUSD", "display_name": "EUR/USD"},
            ])

    def test_binds_tls_transport_and_raw_tick_to_observation(self):
        self.assertTrue(verify_deriv_observation(self.item))
        self.assertEqual(self.item["transport_endpoint"], DERIV_PUBLIC_WS)
        self.assertEqual(self.item["provider"], "Deriv")
        self.assertEqual(self.item["instrument"], "EURUSD")

    def test_rejects_unverified_transport(self):
        item = dict(self.item, transport_security="unverified")
        self.assertFalse(verify_deriv_observation(item))

    def test_rejects_raw_payload_tampering(self):
        item = dict(self.item, raw_message=self.raw.replace("1.08525", "1.99999"))
        self.assertFalse(verify_deriv_observation(item))

    def test_rejects_normalized_price_tampering(self):
        item = dict(self.item, price="1.99999")
        self.assertFalse(verify_deriv_observation(item))

    def test_rejects_wrong_symbol(self):
        item = dict(self.item, deriv_symbol="frxGBPUSD")
        self.assertFalse(verify_deriv_observation(item))

    def test_rejects_non_tick_payload(self):
        raw = json.dumps({"msg_type": "history", "tick": {"symbol": "frxEURUSD"}})
        with self.assertRaises(ValueError):
            build_tick_observation(
                raw, deriv_symbol="frxEURUSD",
                received_at=datetime.now(timezone.utc), tls_verified=True,
            )


if __name__ == "__main__":
    unittest.main()
