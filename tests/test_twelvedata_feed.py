import json
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from research.twelvedata_feed import API_URL, fetch_forex_series


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def payload(*, symbol="EUR/USD", interval="5min", values=None):
    start = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
    if values is None:
        values = []
        for index in range(25):
            price = 1.08 + index * 0.0001
            values.append({
                "datetime": (start + timedelta(minutes=5 * index)).strftime("%Y-%m-%d %H:%M:%S"),
                "open": f"{price:.5f}",
                "high": f"{price + 0.0002:.5f}",
                "low": f"{price - 0.0002:.5f}",
                "close": f"{price + 0.0001:.5f}",
            })
    return {
        "meta": {
            "symbol": symbol,
            "interval": interval,
            "type": "Physical Currency",
            "exchange_timezone": "Australia/Sydney",
        },
        "values": values,
    }


class TwelveDataFeedTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 21, 17, 10, tzinfo=timezone.utc)
        self.captured = {}

    def opener(self, body):
        def open_request(request, timeout):
            self.captured["url"] = request.full_url
            self.captured["headers"] = dict(request.header_items())
            self.captured["timeout"] = timeout
            return FakeResponse(body)
        return open_request

    def test_parses_valid_forex_ohlc_and_keeps_candidate_trust(self):
        result = fetch_forex_series(
            "EUR/USD", api_key="test-key", opener=self.opener(payload()), now=self.now
        )
        self.assertEqual(result.symbol, "EURUSD")
        self.assertEqual(result.interval, "5min")
        self.assertEqual(len(result.candles), 25)
        self.assertLess(result.candles[0].timestamp, result.candles[-1].timestamp)
        self.assertEqual(result.candles[-1].timestamp.tzinfo, timezone.utc)
        self.assertEqual(result.trust_classification, "candidate_unverified")
        self.assertFalse(result.provenance_verified)
        self.assertFalse(result.evidence_credit)
        self.assertEqual(result.licensing_scope, "internal_noncommercial_only")
        provenance = result.provenance()
        self.assertEqual(len(provenance["raw_response_sha256"]), 64)
        self.assertFalse(provenance["evidence_credit"])
        self.assertNotIn("candles", provenance)

    def test_requests_ascending_utc_intraday_data_and_never_returns_api_key(self):
        result = fetch_forex_series(
            "eur-usd", interval="5min", outputsize=30,
            api_key="do-not-leak-this", opener=self.opener(payload()), now=self.now
        )
        query = parse_qs(urlparse(self.captured["url"]).query)
        self.assertEqual(urlparse(self.captured["url"]).scheme, "https")
        self.assertEqual(urlparse(self.captured["url"]).netloc, "api.twelvedata.com")
        self.assertEqual(urlparse(self.captured["url"]).path, "/time_series")
        self.assertEqual(query["timezone"], ["UTC"])
        self.assertEqual(query["order"], ["asc"])
        self.assertEqual(query["include_ohlc"], ["true"])
        self.assertEqual(query["symbol"], ["EUR/USD"])
        self.assertEqual(query["apikey"], ["do-not-leak-this"])
        self.assertNotIn("do-not-leak-this", repr(result.provenance()))

    def test_missing_api_key_fails_before_network_request(self):
        with self.assertRaisesRegex(RuntimeError, "TWELVE_DATA_API_KEY"):
            fetch_forex_series(api_key="", opener=self.opener(payload()), now=self.now)

    def test_rejects_provider_error_and_quota_payload(self):
        for body in (
            {"status": "error", "code": 401, "message": "invalid key"},
            {"Note": "API call frequency limit reached"},
            {"Information": "premium endpoint required"},
        ):
            with self.subTest(body=body):
                with self.assertRaisesRegex(RuntimeError, "API error"):
                    fetch_forex_series(api_key="test-key", opener=self.opener(body), now=self.now)

    def test_rejects_non_forex_instrument_metadata(self):
        wrong_type = payload()
        wrong_type["meta"]["type"] = "Cryptocurrency"
        with self.assertRaisesRegex(ValueError, "Forex/currency"):
            fetch_forex_series(api_key="test-key", opener=self.opener(wrong_type), now=self.now)

    def test_rejects_wrong_symbol_or_interval(self):
        with self.assertRaisesRegex(ValueError, "symbol"):
            fetch_forex_series(api_key="test-key", opener=self.opener(payload(symbol="GBP/USD")), now=self.now)
        with self.assertRaisesRegex(ValueError, "interval"):
            fetch_forex_series(api_key="test-key", opener=self.opener(payload(interval="1min")), now=self.now)

    def test_rejects_bad_ohlc(self):
        bad = payload()
        bad["values"][4]["high"] = "0.5"
        with self.assertRaisesRegex(ValueError, "inconsistent OHLC"):
            fetch_forex_series(api_key="test-key", opener=self.opener(bad), now=self.now)

    def test_rejects_duplicate_or_out_of_order_timestamps(self):
        bad = payload()
        bad["values"][8]["datetime"] = bad["values"][7]["datetime"]
        with self.assertRaisesRegex(ValueError, "ascending and unique"):
            fetch_forex_series(api_key="test-key", opener=self.opener(bad), now=self.now)

    def test_rejects_future_dated_candles(self):
        future = payload()
        future["values"][-1]["datetime"] = "2026-11-21 17:15:00"
        with self.assertRaisesRegex(ValueError, "future-dated"):
            fetch_forex_series(api_key="test-key", opener=self.opener(future), now=self.now)

    def test_rejects_non_forex_symbol_and_unsupported_interval(self):
        with self.assertRaisesRegex(ValueError, "ISO-style"):
            fetch_forex_series("BTC/USDT", api_key="test-key", opener=self.opener(payload()), now=self.now)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            fetch_forex_series(interval="1day", api_key="test-key", opener=self.opener(payload()), now=self.now)

    def test_requires_at_least_twenty_candles(self):
        short = payload(values=payload()["values"][:19])
        with self.assertRaisesRegex(ValueError, "insufficient"):
            fetch_forex_series(api_key="test-key", opener=self.opener(short), now=self.now)


if __name__ == "__main__":
    unittest.main()
