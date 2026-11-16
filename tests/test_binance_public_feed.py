import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlparse

from research.binance_public_feed import fetch_latest_completed_candle


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class BinancePublicFeedTests(unittest.TestCase):
    def setUp(self):
        self.server_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.now = datetime.fromtimestamp((self.server_ms + 1000) / 1000, timezone.utc)
        self.open_ms = self.server_ms - 61_000
        self.close_ms = self.server_ms - 1_000
        self.candle = [
            self.open_ms, "65000.0", "65100.0", "64900.0", "65050.0",
            "12.5", self.close_ms, "812500.0", 100, "5.0", "325000.0", "0",
        ]

    def opener_for(self, candles=None, server_ms=None):
        def opener(request, timeout=10):
            path = urlparse(request.full_url).path
            if path.endswith("/exchangeInfo"):
                return _Response({"symbols": [{
                    "symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True,
                }]})
            if path.endswith("/time"):
                return _Response({"serverTime": server_ms or self.server_ms})
            if path.endswith("/klines"):
                return _Response(candles if candles is not None else [self.candle])
            raise AssertionError("unexpected endpoint")
        return opener

    def test_accepts_latest_completed_candle_and_labels_candidate(self):
        result = fetch_latest_completed_candle(
            opener=self.opener_for(), now=lambda: self.now,
        )
        self.assertEqual(result["instrument"], "BTCUSDT")
        self.assertEqual(result["provider"], "Binance")
        self.assertEqual(result["close"], "65050.0")
        self.assertEqual(result["price"], "65050.0")
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["evidence_credit"])
        self.assertEqual(result["evidence_class"], "unverified_candidate")
        self.assertEqual(len(result["raw_payload_sha256"]), 64)

    def test_ignores_open_candle_and_uses_latest_completed(self):
        open_candle = list(self.candle)
        open_candle[0] = self.server_ms
        open_candle[6] = self.server_ms + 59_000
        result = fetch_latest_completed_candle(
            opener=self.opener_for([self.candle, open_candle]), now=lambda: self.now,
        )
        self.assertEqual(result["provider_event_id"], f"BTCUSDT:1m:{self.open_ms}")

    def test_rejects_when_only_open_candle_is_available(self):
        open_candle = list(self.candle)
        open_candle[0] = self.server_ms
        open_candle[6] = self.server_ms + 59_000
        with self.assertRaisesRegex(ValueError, "fully completed"):
            fetch_latest_completed_candle(
                opener=self.opener_for([open_candle]), now=lambda: self.now,
            )

    def test_rejects_stale_completed_candle(self):
        old = list(self.candle)
        old[0] = self.server_ms - 600_000
        old[6] = self.server_ms - 540_000
        with self.assertRaisesRegex(ValueError, "stale"):
            fetch_latest_completed_candle(
                opener=self.opener_for([old]), now=lambda: self.now,
            )

    def test_rejects_inconsistent_ohlc(self):
        bad = list(self.candle)
        bad[2] = "64000"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            fetch_latest_completed_candle(
                opener=self.opener_for([bad]), now=lambda: self.now,
            )

    def test_rejects_invalid_symbol_and_interval(self):
        with self.assertRaises(ValueError):
            fetch_latest_completed_candle(symbol="../BTC", opener=self.opener_for())
        with self.assertRaises(ValueError):
            fetch_latest_completed_candle(interval="1s", opener=self.opener_for())


if __name__ == "__main__":
    unittest.main()
