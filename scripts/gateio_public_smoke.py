"""Read-only Gate.io public market-data smoke check; never submits orders."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research.gateio_public_feed import BASE_URL, _pair, fetch_latest_completed_candle


def _get(path: str, timeout: float = 10):
    request = Request(BASE_URL + path, headers={
        "Accept": "application/json", "User-Agent": "JarvisUnified-readonly-smoke/1.0",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"public endpoint HTTP {response.status}")
        return json.loads(response.read())


def _positive(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"invalid {label}")
    return number


def run(symbol: str = "BTCUSDT", interval: str = "1m") -> dict:
    pair = _pair(symbol)
    candle = fetch_latest_completed_candle(symbol, interval)
    ticker_rows = _get("/spot/tickers?" + urlencode({"currency_pair": pair}))
    book = _get("/spot/order_book?" + urlencode({"currency_pair": pair, "limit": 1}))
    server = _get("/spot/time")
    if not isinstance(ticker_rows, list) or len(ticker_rows) != 1 or not isinstance(book, dict) or not isinstance(server, dict):
        raise ValueError("malformed Gate.io public market-data response")
    ticker = ticker_rows[0]
    last = _positive(ticker.get("last"), "last price")
    bid = _positive((book.get("bids") or [[None]])[0][0], "best bid")
    ask = _positive((book.get("asks") or [[None]])[0][0], "best ask")
    volume = _positive(ticker.get("base_volume"), "24h base volume")
    if bid > ask or not (bid <= last * Decimal("1.01") and ask >= last * Decimal("0.99")):
        raise ValueError("ticker and best bid/ask are inconsistent")
    server_ms = int(server["server_time"])
    local_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    skew_ms = local_ms - server_ms
    if abs(skew_ms) > 5000:
        raise ValueError("runner clock differs from Gate.io server by more than 5 seconds")
    return {
        "ok": True, "provider": "Gate.io", "source": "gateio-spot-public-rest-v1",
        "symbol": pair, "interval": interval,
        "candle": {
            "event_id": candle["provider_event_id"], "closed_at": candle["observed_at"],
            "close": candle["close"], "volume": candle["volume"],
            "raw_payload_sha256": candle["raw_payload_sha256"],
        },
        "ticker_24h": {
            "last_price": str(last), "price_change_percent": str(ticker.get("change_percentage")),
            "base_volume": str(volume), "quote_volume": str(ticker.get("quote_volume")),
            "high": str(ticker.get("high_24h")), "low": str(ticker.get("low_24h")),
        },
        "best_bid": str(bid), "best_ask": str(ask), "spread": str(ask - bid),
        "server_time": datetime.fromtimestamp(server_ms / 1000, timezone.utc).isoformat(),
        "runner_clock_skew_ms": skew_ms,
        "provenance_verified": False, "evidence_credit": False,
        "mode": "read_only", "trading_actions": 0, "execution_started": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    args = parser.parse_args()
    print(json.dumps(run(args.symbol, args.interval), indent=2))
