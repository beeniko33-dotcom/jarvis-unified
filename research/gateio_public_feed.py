"""Read-only Gate.io Spot completed-candle collector for paper research.

Uses Gate.io public market-data endpoints only. No API key, private account endpoint,
user stream, order endpoint, or trading action is used. Data remains unverified
candidate evidence until independent provenance validation is completed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research.forward_validation import ForwardEvidenceStore

BASE_URL = "https://api.gateio.ws/api/v4"
PROVIDER = "Gate.io"
SOURCE = "gateio-spot-public-rest-v1"
STRATEGY_ID = "sma-crossover-long"
STRATEGY_VERSION = "1.0.0"
ALLOWED_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "8h", "1d"})


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid Gate.io {field}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"Gate.io {field} must be finite and non-negative")
    return result


def _get_json(path: str, *, opener: Callable = urlopen, timeout: float = 10) -> object:
    request = Request(BASE_URL + path, headers={
        "Accept": "application/json",
        "User-Agent": "JarvisUnified-paper-research/1.0",
    })
    try:
        with opener(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise RuntimeError(f"Gate.io market-data HTTP status {response.status}")
            raw = response.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Gate.io public market-data request failed") from exc
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Gate.io returned malformed JSON") from exc


def _pair(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if "_" in symbol:
        parts = symbol.split("_")
        if len(parts) != 2 or not all(p.isalnum() for p in parts):
            raise ValueError("symbol must be a Gate.io currency pair")
        return "_".join(parts)
    if not symbol.isalnum() or len(symbol) < 6:
        raise ValueError("symbol must be an alphanumeric spot pair such as BTCUSDT")
    # Jarvis symbols use USDT quote; require explicit underscore for other quotes.
    if not symbol.endswith("USDT") or len(symbol) <= 4:
        raise ValueError("compact symbols must use the USDT quote; otherwise use BASE_QUOTE")
    return symbol[:-4] + "_USDT"


def fetch_latest_completed_candle(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    *,
    opener: Callable = urlopen,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    max_age_seconds: int = 180,
) -> dict:
    """Fetch and validate the newest fully closed Gate.io candle."""
    pair = _pair(symbol)
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("unsupported Gate.io candle interval")
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be positive")

    server = _get_json("/spot/time", opener=opener)
    if not isinstance(server, dict) or isinstance(server.get("server_time"), bool):
        raise ValueError("Gate.io server-time response is malformed")
    try:
        server_ms = int(server["server_time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Gate.io server-time response is malformed") from exc
    if server_ms <= 0:
        raise ValueError("Gate.io server time must be positive")

    query = urlencode({"currency_pair": pair, "interval": interval, "limit": 5})
    candles = _get_json("/spot/candlesticks?" + query, opener=opener)
    if not isinstance(candles, list) or not candles:
        raise ValueError("Gate.io returned no candle data")

    duration = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                "1h": 3600, "4h": 14400, "8h": 28800, "1d": 86400}[interval]
    completed = []
    for row in candles:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("Gate.io candle row is malformed")
        try:
            start_s = int(row[0])
        except (TypeError, ValueError) as exc:
            raise ValueError("Gate.io candle timestamp is malformed") from exc
        if start_s <= 0:
            raise ValueError("Gate.io candle timestamp must be positive")
        close_ms = (start_s + duration) * 1000
        if close_ms <= server_ms:
            completed.append((start_s, close_ms, row))
    if not completed:
        raise ValueError("Gate.io has not returned a fully completed candle")
    start_s, close_ms, row = max(completed, key=lambda item: item[0])

    # Gate.io array: timestamp, quote volume, close, high, low, open, base amount.
    quote_volume = _decimal(row[1], "quote volume")
    close, high, low, open_price, volume = (
        _decimal(row[index], field)
        for index, field in ((2, "close"), (3, "high"), (4, "low"), (5, "open"), (6, "base volume"))
    )
    if min(open_price, high, low, close) <= 0:
        raise ValueError("Gate.io OHLC prices must be positive")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise ValueError("Gate.io OHLC values are inconsistent")

    received_at = now()
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("collector clock must be timezone-aware")
    received_at = received_at.astimezone(timezone.utc)
    observed_at = datetime.fromtimestamp(close_ms / 1000, timezone.utc)
    server_dt = datetime.fromtimestamp(server_ms / 1000, timezone.utc)
    age = (server_dt - observed_at).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("latest completed Gate.io candle is stale")

    raw_payload = json.dumps(
        {"server_time": server, "candles": [row]},
        sort_keys=True, separators=(",", ":"),
    )
    return {
        "observed_at": observed_at.isoformat(timespec="milliseconds"),
        "collector_received_at": received_at.isoformat(timespec="microseconds"),
        "instrument": pair,
        "provider": PROVIDER,
        "source": SOURCE,
        "interval": interval,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "price": str(close), "open": str(open_price), "high": str(high),
        "low": str(low), "close": str(close), "volume": str(volume),
        "quote_volume": str(quote_volume),
        "provider_event_id": f"{pair}:{interval}:{start_s}",
        "provider_server_time": server_dt.isoformat(),
        "raw_payload": raw_payload,
        "raw_payload_sha256": hashlib.sha256(raw_payload.encode("utf-8")).hexdigest(),
        "provenance_verified": False, "evidence_credit": False,
        "evidence_class": "unverified_candidate",
        "data_kind": "completed_spot_candle",
    }


def collect_once(database: Path, *, symbol: str = "BTCUSDT", interval: str = "1m",
                 opener: Callable = urlopen) -> dict:
    observation = fetch_latest_completed_candle(symbol, interval, opener=opener)
    pair = _pair(symbol)
    store = ForwardEvidenceStore(
        database, instrument=pair, provider=PROVIDER, interval=interval,
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
    )
    try:
        inserted = store.ingest(observation)
        report = store.report(30)
        report.update({
            "collector": SOURCE, "instrument": pair, "interval": interval,
            "inserted": inserted, "trading_actions": 0,
            "provenance_verified": False, "evidence_credit": False,
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
    parser.add_argument("--db", type=Path, default=Path("var/gateio_btcusdt_forward.sqlite3"))
    args = parser.parse_args()
    print(json.dumps(collect_once(args.db, symbol=args.symbol, interval=args.interval), indent=2))
