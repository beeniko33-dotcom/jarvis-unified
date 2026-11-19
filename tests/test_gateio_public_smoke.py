import time
import unittest
from unittest.mock import patch

from scripts import gateio_public_smoke


class GateIoPublicSmokeTests(unittest.TestCase):
    def _candle(self):
        return {
            "provider_event_id": "BTC_USDT:1m:1000",
            "observed_at": "2026-11-18T20:00:00+00:00",
            "close": "65000", "volume": "2", "raw_payload_sha256": "a" * 64,
        }

    def test_reports_public_market_data_without_execution(self):
        responses = iter([
            [{"last": "65001", "change_percentage": "1.2", "base_volume": "10",
              "quote_volume": "650000", "high_24h": "66000", "low_24h": "64000"}],
            {"bids": [["65000", "1"]], "asks": [["65002", "1"]]},
            {"server_time": int(time.time() * 1000)},
        ])
        with patch.object(gateio_public_smoke, "fetch_latest_completed_candle", return_value=self._candle()), \
             patch.object(gateio_public_smoke, "_get", side_effect=lambda _path: next(responses)):
            report = gateio_public_smoke.run()
        self.assertTrue(report["ok"])
        self.assertEqual(report["provider"], "Gate.io")
        self.assertEqual(report["best_bid"], "65000")
        self.assertEqual(report["best_ask"], "65002")
        self.assertEqual(report["trading_actions"], 0)
        self.assertFalse(report["provenance_verified"])

    def test_rejects_inverted_order_book(self):
        responses = iter([
            [{"last": "65001", "base_volume": "10"}],
            {"bids": [["65003", "1"]], "asks": [["65002", "1"]]},
            {"server_time": int(time.time() * 1000)},
        ])
        with patch.object(gateio_public_smoke, "fetch_latest_completed_candle", return_value=self._candle()), \
             patch.object(gateio_public_smoke, "_get", side_effect=lambda _path: next(responses)):
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                gateio_public_smoke.run()


if __name__ == "__main__":
    unittest.main()
