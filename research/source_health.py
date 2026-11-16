"""Deterministic source cadence and outage diagnostics for research observations.

This module reports continuity only. It cannot authenticate a provider, certify
market data, or make observations eligible for strategy scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from datetime import datetime, timezone
from typing import Iterable


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class SourceEvent:
    source_id: str
    event_time: datetime
    duplicate: bool = False
    out_of_order: bool = False
    stale: bool = False
    clock_skew: bool = False

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        _require_aware(self.event_time, "event_time")


@dataclass(frozen=True)
class SourceHealthReport:
    source_id: str
    observations: int
    duplicate_observations: int
    out_of_order_observations: int
    stale_observations: int
    clock_skew_observations: int
    missing_intervals: int
    last_event_at: datetime | None
    seconds_since_last_event: float | None
    outage: bool
    status: str
    provenance: str = "candidate_unverified"
    evidence_eligible: bool = False


def assess_source_health(
    source_id: str,
    events: Iterable[SourceEvent],
    *,
    expected_interval_seconds: int,
    outage_after_seconds: int,
    now: datetime,
) -> SourceHealthReport:
    """Summarize cadence and outage signals without certifying the source.

    Events are sorted by event time. Repeated timestamps do not create extra
    cadence intervals. Missing intervals are estimates based on configured
    cadence, not proof that a provider failed to publish a market event. Each
    gap is rounded to the nearest expected interval (half-up); this avoids
    losing a full missing interval when timestamp delay is close to 2x cadence.
    Duplicate counts reflect only duplicate flags supplied by the caller. A
    persistence layer that discards duplicates cannot reconstruct those events.
    """
    if not source_id.strip():
        raise ValueError("source_id is required")
    if expected_interval_seconds <= 0 or outage_after_seconds <= 0:
        raise ValueError("interval and outage thresholds must be positive")
    _require_aware(now, "now")
    now_utc = now.astimezone(timezone.utc)
    selected = [event for event in events if event.source_id == source_id]
    ordered = sorted(event.event_time.astimezone(timezone.utc) for event in selected)
    unique_times = sorted(set(ordered))

    missing_intervals = 0
    for previous, current in zip(unique_times, unique_times[1:]):
        elapsed = (current - previous).total_seconds()
        # Round to the nearest expected interval (half-up). Small timestamp
        # jitter is absorbed, while a 1.9x cadence gap still counts as 2 slots.
        elapsed_intervals = floor((elapsed / expected_interval_seconds) + 0.5)
        missing_intervals += max(0, elapsed_intervals - 1)

    last_event = unique_times[-1] if unique_times else None
    age = (now_utc - last_event).total_seconds() if last_event else None
    outage = age is None or age > outage_after_seconds

    if not selected:
        status = "NO_DATA"
    elif outage:
        status = "OUTAGE_SUSPECTED"
    elif missing_intervals:
        status = "GAPS_DETECTED"
    else:
        status = "CADENCE_OBSERVED"

    return SourceHealthReport(
        source_id=source_id,
        observations=len(selected),
        duplicate_observations=sum(event.duplicate for event in selected),
        out_of_order_observations=sum(event.out_of_order for event in selected),
        stale_observations=sum(event.stale for event in selected),
        clock_skew_observations=sum(event.clock_skew for event in selected),
        missing_intervals=missing_intervals,
        last_event_at=last_event,
        seconds_since_last_event=age,
        outage=outage,
        status=status,
    )
