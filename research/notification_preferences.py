"""Validation for opt-in PWA notification preferences.

No push subscriptions, private keys, or outbound delivery are handled here.
"""
from __future__ import annotations

from dataclasses import dataclass


CATEGORIES = frozenset({
    "forex_watch", "risk_incident", "system_health", "job_matches",
    "affiliate_updates", "marketplace_updates", "jaeo_tasks",
})


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    enabled: bool
    categories: frozenset[str]
    quiet_start: str | None = None
    quiet_end: str | None = None
    timezone: str = "Africa/Lagos"


def validate_preferences(payload: dict[str, object]) -> NotificationPreferences:
    if not isinstance(payload, dict):
        raise ValueError("preferences must be an object")
    enabled = payload.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be boolean")
    raw_categories = payload.get("categories", [])
    if not isinstance(raw_categories, (list, tuple, set, frozenset)):
        raise ValueError("categories must be a list")
    if any(not isinstance(item, str) for item in raw_categories):
        raise ValueError("categories must contain only strings")
    categories = frozenset(raw_categories)
    if not categories <= CATEGORIES:
        raise ValueError("unknown notification category")
    quiet_start = payload.get("quiet_start")
    quiet_end = payload.get("quiet_end")
    for name, value in (("quiet_start", quiet_start), ("quiet_end", quiet_end)):
        if value is not None and (
            not isinstance(value, str)
            or len(value) != 5
            or value[2] != ":"
            or not value[:2].isdigit()
            or not value[3:].isdigit()
            or not (0 <= int(value[:2]) <= 23 and 0 <= int(value[3:]) <= 59)
        ):
            raise ValueError(f"{name} must use HH:MM")
    if (quiet_start is None) != (quiet_end is None):
        raise ValueError("quiet hours require both start and end")
    timezone = payload.get("timezone", "Africa/Lagos")
    if not isinstance(timezone, str) or not timezone or len(timezone) > 64:
        raise ValueError("timezone must be a valid non-empty identifier")
    if not enabled and categories:
        # Preserve selected categories only when opted in; avoid accidental delivery.
        raise ValueError("categories cannot be active while notifications are disabled")
    return NotificationPreferences(
        enabled=enabled,
        categories=categories,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        timezone=timezone,
    )
