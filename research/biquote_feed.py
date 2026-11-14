"""Biquote SignalR EURUSD candidate collector.

This feed is indicative and aggregated. This module records candidate-only observations;
it cannot authenticate individual ticks and never grants Level 3 evidence credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

BIQUOTE_HUB = "https://biquote.io/hubs/tick"
PROVIDER = "Biquote"
INSTRUMENT = "EURUSD"
SOURCE_PREFIX = "biquote-signalr:"
STRATEGY_ID = "sma-crossover-long"
STRATEGY_VERSION = "1.0.0"


def _utc_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite number") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return result


def build_tick_observation(
    tick: dict,
    *,
    received_at: datetime,
    max_quote_age_seconds: int = 120,
    future_tolerance_seconds: int = 30,
) -> dict:
    """Validate a Biquote event's shape/freshness; never authenticate its origin."""
    if not isinstance(tick, dict):
        raise ValueError("Biquote tick must be a JSON object")
    if tick.get("symbol") != INSTRUMENT:
        raise ValueError("Biquote symbol must be exactly EURUSD")

    source = tick.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Biquote source metadata is required")

    if tick.get("stale") is not False:
        raise ValueError("stale or unspecified Biquote quote rejected")
    if tick.get("marketState") != "open":
        raise ValueError("Biquote market must be open for forward candidate ingestion")

    try:
        quote_age = Decimal(str(tick["quoteAgeSeconds"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("quoteAgeSeconds is required and must be numeric") from exc
    if not quote_age.is_finite() or quote_age < 0 or quote_age > max_quote_age_seconds:
        raise ValueError("Biquote quote is stale or has invalid quote age")

    observed = _utc_datetime(tick.get("timestamp"), "timestamp")
    if not isinstance(received_at, datetime) or received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("collector receive time must be timezone-aware")
    received = received_at.astimezone(timezone.utc)
    age = (received - observed).total_seconds()
    if age < -future_tolerance_seconds:
        raise ValueError("Biquote timestamp is too far in the future")
    if age > max_quote_age_seconds:
        raise ValueError("Biquote timestamp is stale")

    bid = _positive_decimal(tick.get("bid"), "bid")
    ask = _positive_decimal(tick.get("ask"), "ask")
    mid = _positive_decimal(tick.get("mid"), "mid")
    if ask < bid or not bid <= mid <= ask:
        raise ValueError("Biquote bid/ask/mid relationship is invalid")

    raw_payload = json.dumps(tick, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
    return {
        "observed_at": observed.isoformat(timespec="microseconds"),
        "instrument": INSTRUMENT,
        "provider": PROVIDER,
        "source": SOURCE_PREFIX + source.strip(),
        "interval": "tick",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "price": str(mid),
        "bid": str(bid),
        "ask": str(ask),
        "mid": str(mid),
        "provider_source_label": source.strip(),
        "provider_timestamp": observed.isoformat(timespec="microseconds"),
        "collector_received_at": received.isoformat(timespec="microseconds"),
        "quote_age_seconds_at_source": str(quote_age),
        "market_state": "open",
        "provider_event_id": None,
        "raw_payload": raw_payload,
        "raw_payload_sha256": digest,
        "trust_classification": "candidate_unverified",
        "evidence_credit": False,
        "provenance_verified": False,
    }


def collect(
    duration_seconds: int,
    database: Path,
    *,
    max_quote_age_seconds: int = 120,
) -> dict:
    """Collect public Biquote SignalR events for a bounded session."""
    if duration_seconds < 1:
        raise ValueError("duration_seconds must be positive")
    try:
        from signalrcore.hub_connection_builder import HubConnectionBuilder
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install -e '.[market-data]'") from exc

    from research.forward_validation import ForwardEvidenceStore

    store = ForwardEvidenceStore(
        database,
        instrument=INSTRUMENT,
        provider=PROVIDER,
        interval="tick",
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        max_observation_age=timedelta(seconds=max_quote_age_seconds),
        future_tolerance=timedelta(seconds=30),
    )
    stop_at = time.monotonic() + duration_seconds
    finished = threading.Event()
    lock = threading.Lock()
    counts = {"inserted": 0, "duplicates": 0, "rejected": 0, "received": 0}
    connection = None

    def on_tick(tick):
        with lock:
            counts["received"] += 1
        try:
            item = build_tick_observation(
                tick,
                received_at=datetime.now(timezone.utc),
                max_quote_age_seconds=max_quote_age_seconds,
            )
            added = store.ingest(item)
            with lock:
                counts["inserted" if added else "duplicates"] += 1
        except (ValueError, TypeError, KeyError):
            with lock:
                counts["rejected"] += 1

    def subscribe():
        # SignalR's on_open callback also runs after a successful reconnect.
        connection.send("Subscribe", [INSTRUMENT])

    connection = (
        HubConnectionBuilder()
        .with_url(BIQUOTE_HUB)
        .with_automatic_reconnect({
            "type": "raw",
            "keep_alive_interval": 10,
            "reconnect_interval": 5,
            "max_attempts": 5,
        })
        .build()
    )
    connection.on("ReceiveTick", on_tick)
    connection.on_open(subscribe)
    try:
        connection.start()
        while time.monotonic() < stop_at:
            time.sleep(min(0.5, max(0.0, stop_at - time.monotonic())))
        finished.set()
    finally:
        finished.set()
        try:
            connection.stop()
        finally:
            report = store.report(30)
            with lock:
                report.update(counts)
            report.update({
                "collector": "Biquote public SignalR read-only",
                "instrument": INSTRUMENT,
                "trust_classification": "candidate_unverified",
                "evidence_credit": False,
                "trading_actions": 0,
                "account_authentication_used": False,
                "level_3_certification": False,
            })
            store.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--db", type=Path, default=Path("var/biquote_eurusd_candidates.sqlite3"))
    parser.add_argument("--max-quote-age-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.max_quote_age_seconds < 1:
        parser.error("duration and max quote age must be positive")
    report = collect(
        args.duration_seconds,
        args.db,
        max_quote_age_seconds=args.max_quote_age_seconds,
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("event_chain_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
