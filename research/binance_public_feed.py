"""Read-only Binance Spot completed-candle collector for paper research.

Uses Binance's documented market-data-only REST host. No API key, account endpoint,
user stream, order endpoint, or trading action is used. Candles are source-attributed
observations, not independently authenticated/signed evidence; the evidence store
must continue to classify them as unverified candidates.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from research.forward_validation import ForwardEvidenceStore

BASE_URL = "https://data-api.binance.vision"
PROVIDER = "Binance"
SOURCE = "binance-spot-public-rest-v1"
STRATEGY_ID = "sma-crossover-long"
STRATEGY_VERSION = "1.0.0"
ALLOWED_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid Binance {field}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"Binance {field} must be finite and non-negative")
    return result


def _get_json(path: str, *, opener: Callable = urlopen, timeout: float = 10) -> object:
    request = Request(
        BASE_URL + path,
        headers={"Accept": "application/json", "User-Agent": "JarvisUnified-paper-research/1.0"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise RuntimeError(f"Binance market-data HTTP status {response.status}")
            raw = response.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Binance public market-data request failed") from exc
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Binance returned malformed JSON") from exc


def fetch_latest_completed_candle(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    *,
    opener: Callable = urlopen,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    max_age_seconds: int = 180,
) -> dict:
    """Fetch and validate the newest fully closed candle; never accepts an open candle."""
    symbol = symbol.strip().upper()
    if not symbol or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric Binance spot symbol")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("unsupported candle interval")
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be positive")

    from urllib.parse import urlencode
    query = urlencode({"symbol": symbol})
    exchange_info = _get_json("/api/v3/exchangeInfo?" + query, opener=opener)
    if not isinstance(exchange_info, dict) or not isinstance(exchange_info.get("symbols"), list):
        raise ValueError("Binance exchangeInfo response is malformed")
    listed = [item for item in exchange_info["symbols"] if isinstance(item, dict) and item.get("symbol") == symbol]
    if len(listed) != 1 or listed[0].get("status") != "TRADING" or listed[0].get("isSpotTradingAllowed") is not True:
        raise ValueError("Binance symbol is not uniquely listed and enabled for Spot trading")

    server = _get_json("/api/v3/time", opener=opener)
    if not isinstance(server, dict) or isinstance(server.get("serverTime"), bool):
        raise ValueError("Binance server-time response is malformed")
    try:
        server_ms = int(server["serverTime"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Binance server-time response is malformed") from exc
    if server_ms <= 0:
        raise ValueError("Binance server time must be positive")

    query = urlencode({"symbol": symbol, "interval": interval, "limit": 3})
    candles = _get_json("/api/v3/klines?" + query, opener=opener)
    if not isinstance(candles, list) or not candles:
        raise ValueError("Binance returned no candle data")

    completed = []
    for row in candles:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("Binance candle row is malformed")
        try:
            open_ms, close_ms = int(row[0]), int(row[6])
        except (TypeError, ValueError) as exc:
            raise ValueError("Binance candle timestamps are malformed") from exc
        if close_ms < open_ms or open_ms <= 0:
            raise ValueError("Binance candle timestamp range is invalid")
        if close_ms < server_ms:
            completed.append(row)
    if not completed:
        raise ValueError("Binance has not returned a fully completed candle")
    row = max(completed, key=lambda item: int(item[6]))
    open_price, high, low, close, volume = (
        _decimal(row[index], field)
        for index, field in ((1, "open"), (2, "high"), (3, "low"), (4, "close"), (5, "volume"))
    )
    if min(open_price, high, low, close) <= 0:
        raise ValueError("Binance OHLC prices must be positive")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise ValueError("Binance OHLC values are inconsistent")

    received_at = now()
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("collector clock must be timezone-aware")
    received_at = received_at.astimezone(timezone.utc)
    observed_at = datetime.fromtimestamp(int(row[6]) / 1000, timezone.utc)
    age = (datetime.fromtimestamp(server_ms / 1000, timezone.utc) - observed_at).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("latest completed Binance candle is stale")

    raw_payload = json.dumps(
        {"server_time": server, "candles": [row]},
        sort_keys=True, separators=(",", ":"),
    )
    return {
        "observed_at": observed_at.isoformat(timespec="milliseconds"),
        "collector_received_at": received_at.isoformat(timespec="microseconds"),
        "instrument": symbol,
        "provider": PROVIDER,
        "source": SOURCE,
        "interval": interval,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "price": str(close),
        "open": str(open_price),
        "high": str(high),
        "low": str(low),
        "close": str(close),
        "volume": str(volume),
        "provider_event_id": f"{symbol}:{interval}:{int(row[0])}",
        "provider_server_time": datetime.fromtimestamp(server_ms / 1000, timezone.utc).isoformat(),
        "raw_payload": raw_payload,
        "raw_payload_sha256": hashlib.sha256(raw_payload.encode("utf-8")).hexdigest(),
        "provenance_verified": False,
        "evidence_credit": False,
        "evidence_class": "unverified_candidate",
        "data_kind": "completed_spot_candle",
    }


def collect_once(
    database: Path,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    opener: Callable = urlopen,
) -> dict:
    """Persist one fresh completed candle in the existing fail-closed evidence store."""
    observation = fetch_latest_completed_candle(symbol, interval, opener=opener)
    store = ForwardEvidenceStore(
        database,
        instrument=symbol.upper(),
        provider=PROVIDER,
        interval=interval,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
    )
    try:
        inserted = store.ingest(observation)
        report = store.report(30)
        report.update({
            "collector": SOURCE,
            "instrument": symbol.upper(),
            "interval": interval,
            "inserted": inserted,
            "trading_actions": 0,
            "provenance_verified": False,
            "evidence_credit": False,
            "execution_started": False,
        })
        return report
    finally:
        store.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m", choices=sorted(ALLOWED_INTERVALS))
    parser.add_argument("--db", type=Path, default=Path("var/binance_btcusdt_forward.sqlite3"))
    args = parser.parse_args()
    print(json.dumps(collect_once(args.db, symbol=args.symbol, interval=args.interval), indent=2))
