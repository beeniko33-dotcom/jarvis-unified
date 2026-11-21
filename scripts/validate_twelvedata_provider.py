#!/usr/bin/env python3
"""One-shot private Twelve Data provider check; prints metadata, never raw quotes."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from research.twelvedata_feed import fetch_forex_series


def main() -> int:
    if not os.environ.get("TWELVE_DATA_API_KEY"):
        print(json.dumps({"status": "blocked", "reason": "TWELVE_DATA_API_KEY is not configured"}))
        return 2
    symbol = os.environ.get("TWELVE_DATA_SYMBOL", "EUR/USD")
    interval = os.environ.get("TWELVE_DATA_INTERVAL", "5min")
    try:
        series = fetch_forex_series(
            symbol,
            interval=interval,
            outputsize=int(os.environ.get("TWELVE_DATA_OUTPUTSIZE", "50")),
        )
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "provider": "Twelve Data",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "provenance_verified": False,
            "evidence_credit": False,
        }, indent=2))
        return 1

    latest = series.candles[-1].timestamp
    fetched = datetime.fromisoformat(series.fetched_at)
    report = {
        "status": "provider_response_validated",
        "provider": series.provider,
        "feed": series.feed,
        "symbol": series.symbol,
        "interval": series.interval,
        "candle_count": len(series.candles),
        "first_candle_utc": series.candles[0].timestamp.isoformat(),
        "latest_candle_utc": latest.isoformat(),
        "retrieved_at_utc": series.fetched_at,
        "latest_candle_age_seconds": max(0, int((fetched - latest).total_seconds())),
        "provider_metadata": series.provider_metadata,
        "raw_response_sha256": series.raw_response_sha256,
        "trust_classification": series.trust_classification,
        "licensing_scope": series.licensing_scope,
        "provenance_verified": False,
        "evidence_credit": False,
        "note": "Successful API response and OHLC validation do not independently authenticate upstream liquidity-provider lineage.",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
