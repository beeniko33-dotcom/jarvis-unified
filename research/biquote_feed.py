"""Biquote SignalR EURUSD candidate collector.

This feed is indicative and aggregated. It records candidate-only observations;
it cannot authenticate individual ticks and never grants Level 3 evidence credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import queue
import time
import threading
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
MAX_PENDING_TICKS = 10_000


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


def unwrap_tick_arguments(arguments: Any) -> dict:
    """Normalise a SignalR invocation payload into a single tick object.

    ``signalrcore`` invokes a registered handler as ``handler(message.arguments)``,
    where ``message.arguments`` is the JSON array from the hub frame. Passing that
    list straight to :func:`build_tick_observation` rejected every real tick, so
    the dispatch boundary is normalised here instead of inside the validator.

    A bare dict is accepted for direct callers. Anything else fails closed: an
    empty or multi-argument frame is ambiguous and must not be guessed at.
    """
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, (list, tuple)):
        raise ValueError("Biquote tick frame must be a JSON object or a one-element array")
    if len(arguments) != 1:
        raise ValueError(
            f"Biquote tick frame must carry exactly one argument, got {len(arguments)}"
        )
    tick = arguments[0]
    if not isinstance(tick, dict):
        raise ValueError("Biquote tick frame argument must be a JSON object")
    return tick


def build_tick_observation(
    tick: dict,
    *,
    received_at: datetime,
    max_quote_age_seconds: int = 120,
    future_tolerance_seconds: int = 30,
) -> dict:
    """Validate an event's shape and freshness; never authenticate its origin."""
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

    # This is a canonical JSON serialization digest, not a hash of original
    # WebSocket wire bytes and not proof of provider origin.
    canonical_payload = json.dumps(tick, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
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
        "raw_payload": canonical_payload,
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
    """Collect public Biquote SignalR events for a bounded session.

    SignalR callbacks run outside the collector's main thread. They only enqueue
    bounded events; all SQLite access stays on the main thread.
    """
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
    pending: queue.Queue = queue.Queue(maxsize=MAX_PENDING_TICKS)
    lock = threading.Lock()
    counts = {
        "inserted": 0, "duplicates": 0, "rejected": 0,
        "received": 0, "dropped_queue_full": 0,
    }
    connection = None
    report = None

    def on_tick(arguments):
        # signalrcore delivers message.arguments (a list), not the tick itself.
        with lock:
            counts["received"] += 1
        try:
            pending.put_nowait(arguments)
        except queue.Full:
            with lock:
                counts["dropped_queue_full"] += 1

    def process_tick(arguments):
        try:
            item = build_tick_observation(
                unwrap_tick_arguments(arguments),
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
        # on_open is called after initial connection and successful reconnect.
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
    stop_at = time.monotonic() + duration_seconds
    try:
        connection.start()
        while time.monotonic() < stop_at:
            remaining = max(0.0, stop_at - time.monotonic())
            try:
                tick = pending.get(timeout=min(0.5, remaining))
            except queue.Empty:
                continue
            process_tick(tick)
        connection.stop()
        connection = None
        # Drain events already delivered before closing the store.
        while True:
            try:
                process_tick(pending.get_nowait())
            except queue.Empty:
                break
    finally:
        if connection is not None:
            try:
                connection.stop()
            except Exception:
                pass
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
            "queue_capacity": MAX_PENDING_TICKS,
        })
        # A valid hash chain only proves stored-row integrity. Queue overflow or
        # rejected events means the observed stream was not fully ingested.
        report["collection_integrity"] = (
            "degraded" if report["dropped_queue_full"] > 0 or report["rejected"] > 0
            else "candidate_observed" if report["inserted"] > 0
            else "no_usable_ticks"
        )
        store.close()
    return report


def collection_exit_code(report: dict) -> int:
    """Return success only for observed, non-degraded candidate collection."""
    return 0 if (
        report.get("event_chain_valid")
        and report.get("inserted", 0) > 0
        and report.get("dropped_queue_full", 0) == 0
        and report.get("rejected", 0) == 0
        and report.get("collection_integrity") == "candidate_observed"
    ) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--db", type=Path, default=Path("var/biquote_eurusd_candidates.sqlite3"))
    parser.add_argument("--max-quote-age-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.max_quote_age_seconds < 1:
        parser.error("duration and max quote age must be positive")
    result = collect(
        args.duration_seconds,
        args.db,
        max_quote_age_seconds=args.max_quote_age_seconds,
    )
    print(json.dumps(result, indent=2))
    # A valid empty hash chain is not proof the collector received usable data.
    return collection_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
