"""Twelve Data Forex time-series adapter for private research validation.

This adapter does not persist or publish market data and never upgrades trust.
Twelve Data's free/individual plans are for internal, non-commercial use only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from research.forex_forecast import Candle

API_URL = "https://api.twelvedata.com/time_series"
PROVIDER = "Twelve Data"
FEED = "Twelve Data Forex API v2 composite feed"
ALLOWED_INTERVALS = frozenset({"1min", "5min", "15min", "30min", "1h"})


@dataclass(frozen=True, slots=True)
class TwelveDataSeries:
    symbol: str
    interval: str
    candles: tuple[Candle, ...]
    fetched_at: str
    provider: str
    feed: str
    provider_metadata: dict[str, str]
    raw_response_sha256: str
    trust_classification: str = "candidate_unverified"
    licensing_scope: str = "internal_noncommercial_only"
    provenance_verified: bool = False
    evidence_credit: bool = False

    def provenance(self) -> dict[str, Any]:
        """Return provenance metadata without copying the underlying candle feed."""
        return {
            "provider": self.provider,
            "feed": self.feed,
            "symbol": self.symbol,
            "interval": self.interval,
            "fetched_at": self.fetched_at,
            "provider_metadata": dict(self.provider_metadata),
            "raw_response_sha256": self.raw_response_sha256,
            "raw_response_hash_scope": "decoded HTTP response bytes; integrity only, not origin authentication",
            "trust_classification": self.trust_classification,
            "licensing_scope": self.licensing_scope,
            "provenance_verified": False,
            "evidence_credit": False,
        }


def _canonical_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a currency pair")
    normalized = symbol.strip().upper().replace("-", "/").replace("_", "/")
    if not re.fullmatch(r"[A-Z]{3}/[A-Z]{3}", normalized):
        raise ValueError("symbol must use an ISO-style pair such as EUR/USD")
    base, quote = normalized.split("/")
    if base == quote:
        raise ValueError("base and quote currencies must differ")
    return normalized


def _provider_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider candle datetime is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("provider candle datetime is invalid") from exc
    # The request explicitly asks Twelve Data for timezone=UTC. Forex intraday
    # values are returned in UTC; naive strings are therefore bound to that
    # requested timezone, never to the collector machine's local timezone.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _positive_outputsize(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 20 <= value <= 5000:
        raise ValueError("outputsize must be an integer between 20 and 5000")
    return value


def fetch_forex_series(
    symbol: str = "EUR/USD",
    *,
    interval: str = "5min",
    outputsize: int = 50,
    api_key: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: datetime | None = None,
    timeout_seconds: int = 10,
) -> TwelveDataSeries:
    """Fetch and validate an ascending UTC Forex OHLC series.

    The API key is read from TWELVE_DATA_API_KEY by default. It is sent only to
    api.twelvedata.com and is never included in returned errors or metadata.
    """
    pair = _canonical_symbol(symbol)
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("unsupported intraday Forex interval")
    count = _positive_outputsize(outputsize)
    key = (api_key or os.environ.get("TWELVE_DATA_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required for live provider validation")
    if timeout_seconds < 1 or timeout_seconds > 60:
        raise ValueError("timeout_seconds must be between 1 and 60")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("collector clock must be timezone-aware")
    fetched_at = clock.astimezone(timezone.utc)

    params = urllib.parse.urlencode({
        "symbol": pair,
        "interval": interval,
        "outputsize": str(count),
        "timezone": "UTC",
        "order": "asc",
        "include_ohlc": "true",
        "format": "JSON",
        "apikey": key,
    })
    request = urllib.request.Request(
        API_URL + "?" + params,
        headers={
            "Accept": "application/json",
            "User-Agent": "JarvisUnified-ForexResearch/0.2",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Twelve Data HTTP request failed with status {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Twelve Data network request failed: {type(exc).__name__}") from None

    if not 200 <= int(status) < 300:
        raise RuntimeError(f"Twelve Data HTTP request failed with status {status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Twelve Data response was not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("Twelve Data response must be a JSON object")
    if payload.get("status") == "error" or ("values" not in payload and any(
        k in payload for k in ("code", "message", "Note", "Information", "note", "information")
    )):
        # Do not echo provider messages: some gateways can reflect request details.
        raise RuntimeError("Twelve Data returned an API error or entitlement/rate-limit response")

    meta = payload.get("meta")
    values = payload.get("values")
    if not isinstance(meta, dict) or not isinstance(values, list):
        raise ValueError("Twelve Data response is missing meta or values")
    returned_symbol = _canonical_symbol(str(meta.get("symbol", "")))
    if returned_symbol != pair:
        raise ValueError("Twelve Data response symbol does not match the requested pair")
    if str(meta.get("interval", "")).lower() != interval.lower():
        raise ValueError("Twelve Data response interval does not match the requested interval")
    instrument_type = str(meta.get("type", "")).strip().lower()
    if "crypto" in instrument_type or not instrument_type or not any(
        term in instrument_type for term in ("currency", "forex")
    ):
        raise ValueError("Twelve Data response does not identify a Forex/currency instrument")
    if len(values) < 20 or len(values) > count:
        raise ValueError("Twelve Data returned an insufficient or unexpected candle count")

    candles: list[Candle] = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("Twelve Data candle must be a JSON object")
        timestamp = _provider_timestamp(item.get("datetime"))
        candles.append(Candle.from_values(
            timestamp,
            item.get("open"),
            item.get("high"),
            item.get("low"),
            item.get("close"),
        ))
    if any(a.timestamp >= b.timestamp for a, b in zip(candles, candles[1:])):
        raise ValueError("Twelve Data candles must be strictly ascending and unique")
    if candles[-1].timestamp > fetched_at.replace(microsecond=0):
        raise ValueError("Twelve Data returned a future-dated candle")

    metadata = {}
    for key_name in ("type", "exchange", "exchange_timezone", "currency_base", "currency_quote"):
        value = meta.get(key_name)
        if isinstance(value, str) and value.strip():
            metadata[key_name] = value.strip()
    raw_hash = hashlib.sha256(raw).hexdigest()
    return TwelveDataSeries(
        symbol=pair.replace("/", ""),
        interval=interval,
        candles=tuple(candles),
        fetched_at=fetched_at.isoformat(),
        provider=PROVIDER,
        feed=FEED,
        provider_metadata=metadata,
        raw_response_sha256=raw_hash,
    )
