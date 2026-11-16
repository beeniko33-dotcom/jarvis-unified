import unittest
import time
from unittest.mock import patch

from scripts import binance_public_smoke


class BinancePublicSmokeTests(unittest.TestCase):
    def test_reports_market_data_without_execution(self):
        candle = {
            "provider_event_id": "BTCUSDT:1m:1000",
            "observed_at": "2026-11-16T20:00:00+00:00",
            "close": "65000",
            "volume": "2",
            "raw_payload_sha256": "a" * 64,
        }
        responses = iter([
            {"lastPrice": "65001", "priceChangePercent": "1.2", "volume": "10",
             "quoteVolume": "650000", "highPrice": "66000", "lowPrice": "64000"},
            {"bidPrice": "65000", "askPrice": "65002"},
            {"serverTime": int(time.time() * 1000)},
        ])
        with patch.object(binance_public_smoke, "fetch_latest_completed_candle", return_value=candle), \
             patch.object(binance_public_smoke, "_get", side_effect=lambda _path: next(responses)), \
            report = binance_public_smoke.run()
        self.assertTrue(report["ok"])
        self.assertEqual(report["best_bid"], "65000")
        self.assertEqual(report["best_ask"], "65002")
        self.assertEqual(report["trading_actions"], 0)
        self.assertFalse(report["provenance_verified"])

    def test_rejects_inverted_book(self):
        candle = {
            "provider_event_id": "BTCUSDT:1m:1000",
            "observed_at": "2026-11-16T20:00:00+00:00",
            "close": "65000",
            "volume": "2",
            "raw_payload_sha256": "a" * 64,
        }
        responses = iter([
            {"lastPrice": "65001", "volume": "10"},
            {"bidPrice": "65003", "askPrice": "65002"},
            {"serverTime": 1794859200000},
        ])
        with patch.object(binance_public_smoke, "fetch_latest_completed_candle", return_value=candle), \
             patch.object(binance_public_smoke, "_get", side_effect=lambda _path: next(responses)), \
             patch.object(binance_public_smoke.datetime, "now", return_value=binance_public_smoke.datetime.fromtimestamp(1794859200, binance_public_smoke.timezone.utc)):
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                binance_public_smoke.run()


if __name__ == "__main__":
    unittest.main()
