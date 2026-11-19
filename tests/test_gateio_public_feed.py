import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from research.gateio_public_feed import fetch_latest_completed_candle


class _Response:
    status = 200
    def __init__(self, payload): self.payload = json.dumps(payload).encode()
    def read(self): return self.payload
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class GateIoPublicFeedTests(unittest.TestCase):
    def setUp(self):
        self.server_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.now = datetime.fromtimestamp(self.server_ms / 1000, timezone.utc)
        self.start_s = self.server_ms // 1000 - 120
        self.candle = [str(self.start_s), "1250000", "65050", "65100", "64900", "65000", "19.2"]

    def opener_for(self, candles=None, server_ms=None):
        def opener(request, timeout=10):
            path = urlparse(request.full_url).path
            if path.endswith("/spot/time"):
                return _Response({"server_time": server_ms or self.server_ms})
            if path.endswith("/spot/candlesticks"):
                query = parse_qs(urlparse(request.full_url).query)
                self.assertEqual(query["currency_pair"], ["BTC_USDT"])
                return _Response(candles if candles is not None else [self.candle])
            raise AssertionError("unexpected endpoint")
        return opener

    def test_accepts_latest_completed_candle_as_unverified_candidate(self):
        result = fetch_latest_completed_candle(opener=self.opener_for(), now=lambda: self.now)
        self.assertEqual(result["instrument"], "BTC_USDT")
        self.assertEqual(result["provider"], "Gate.io")
        self.assertEqual(result["close"], "65050")
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["evidence_credit"])
        self.assertEqual(result["evidence_class"], "unverified_candidate")
        self.assertEqual(len(result["raw_payload_sha256"]), 64)

    def test_ignores_open_candle(self):
        opened = [str(self.server_ms // 1000), "100", "65000", "65100", "64900", "65000", "1"]
        result = fetch_latest_completed_candle(
            opener=self.opener_for([self.candle, opened]), now=lambda: self.now,
        )
        self.assertEqual(result["provider_event_id"], f"BTC_USDT:1m:{self.start_s}")

    def test_rejects_only_open_candle(self):
        opened = [str(self.server_ms // 1000), "100", "65000", "65100", "64900", "65000", "1"]
        with self.assertRaisesRegex(ValueError, "fully completed"):
            fetch_latest_completed_candle(opener=self.opener_for([opened]), now=lambda: self.now)

    def test_rejects_stale_candle(self):
        old = list(self.candle)
        old[0] = str(self.server_ms // 1000 - 600)
        with self.assertRaisesRegex(ValueError, "stale"):
            fetch_latest_completed_candle(opener=self.opener_for([old]), now=lambda: self.now)

    def test_rejects_invalid_ohlc_and_pair(self):
        bad = list(self.candle); bad[3] = "64000"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            fetch_latest_completed_candle(opener=self.opener_for([bad]), now=lambda: self.now)
        with self.assertRaises(ValueError):
            fetch_latest_completed_candle(symbol="../BTC", opener=self.opener_for())


if __name__ == "__main__":
    unittest.main()
