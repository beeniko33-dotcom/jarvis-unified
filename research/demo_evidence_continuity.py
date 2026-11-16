"""UTC continuity accounting for future authenticated demo-evidence ingestion.

This module counts consecutive calendar days with an explicit heartbeat record.
It does not authenticate the provider/account or establish evidence eligibility.
Its inputs must be supplied by a separately trusted ingestion boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


class DemoContinuityError(ValueError):
    """A daily evidence record is malformed or ambiguous."""


@dataclass(frozen=True)
class DailyDemoHeartbeat:
    utc_day: str
    heartbeat_event_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.utc_day, str):
            raise DemoContinuityError("utc_day must be an ISO-8601 date string")
        try:
            parsed = date.fromisoformat(self.utc_day)
        except ValueError as exc:
            raise DemoContinuityError("utc_day must be an ISO-8601 date string") from exc
        if parsed.isoformat() != self.utc_day:
            raise DemoContinuityError("utc_day must use canonical YYYY-MM-DD format")
        if not isinstance(self.heartbeat_event_id, str) or not self.heartbeat_event_id.strip():
            raise DemoContinuityError("heartbeat_event_id is required")


@dataclass(frozen=True)
class DemoContinuityReport:
    as_of_utc_day: str
    consecutive_utc_days: int
    latest_heartbeat_utc_day: str | None
    observed_days: int
    missing_days_in_streak: int
    status: str = "CONTINUITY_ONLY_NOT_AUTHENTICATED"
    provider_authenticity_verified: int = 0
    evidence_eligible: bool = False


def assess_demo_continuity(
    heartbeats: Iterable[DailyDemoHeartbeat], *, as_of_utc_day: str
) -> DemoContinuityReport:
    """Count the uninterrupted heartbeat streak ending on ``as_of_utc_day``.

    A day is present only when an explicit daily heartbeat exists. Missing days,
    duplicate day records, malformed dates, or future-dated records are never
    silently repaired or inferred. The caller must independently verify the
    source ledger and demo account before treating these counts as evidence.
    """
    try:
        as_of = date.fromisoformat(as_of_utc_day)
    except (TypeError, ValueError) as exc:
        raise DemoContinuityError("as_of_utc_day must be an ISO-8601 date") from exc
    if as_of.isoformat() != as_of_utc_day:
        raise DemoContinuityError("as_of_utc_day must use canonical YYYY-MM-DD format")

    by_day: dict[date, DailyDemoHeartbeat] = {}
    event_ids: set[str] = set()
    for item in heartbeats:
        if not isinstance(item, DailyDemoHeartbeat):
            raise TypeError("heartbeats must contain DailyDemoHeartbeat records")
        day = date.fromisoformat(item.utc_day)
        if day > as_of:
            raise DemoContinuityError("future-dated heartbeat is not allowed")
        if day in by_day:
            raise DemoContinuityError("duplicate heartbeat day")
        if item.heartbeat_event_id in event_ids:
            raise DemoContinuityError("heartbeat event IDs must be unique")
        by_day[day] = item
        event_ids.add(item.heartbeat_event_id)

    latest = max(by_day) if by_day else None
    streak = 0
    cursor = as_of
    while cursor in by_day:
        streak += 1
        cursor -= timedelta(days=1)

    return DemoContinuityReport(
        as_of_utc_day=as_of_utc_day,
        consecutive_utc_days=streak,
        latest_heartbeat_utc_day=latest.isoformat() if latest else None,
        observed_days=len(by_day),
        missing_days_in_streak=0 if streak else 1,
    )
