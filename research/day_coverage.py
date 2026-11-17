"""UTC-day coverage and streak assessment shared by the paper-validation checks.

Pure functions: no clock, no I/O. Callers pass the dates on which sessions happened and the
UTC date being assessed. This reports coverage; it never repairs, backfills or credits days.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def assess_days(days: list[date], as_of: date) -> dict[str, Any]:
    """Assess session-day coverage as of a UTC date.

    ``state`` is one of: ``ok`` (a session on ``as_of``), ``missing_today`` (yesterday was the
    last session, so the streak is alive), ``streak_broken`` (older than yesterday) or
    ``future_dated`` (a session after ``as_of``).
    """
    unique = sorted(set(days))
    if not unique:
        raise ValueError("no session days to assess")
    first, last = unique[0], unique[-1]
    span = max((as_of - first).days + 1, 0)
    expected = {first + timedelta(days=i) for i in range(span)}
    missing = sorted(expected - set(unique))

    streak = 1
    for previous, current in zip(reversed(unique[:-1]), reversed(unique[1:])):
        if (current - previous).days == 1:
            streak += 1
        else:
            break

    alerts: list[str] = []
    if last > as_of:
        state = "future_dated"
        alerts.append(f"events dated after {as_of.isoformat()}")
    elif last == as_of:
        state = "ok"
    elif last == as_of - timedelta(days=1):
        state = "missing_today"
        alerts.append(f"no session recorded yet for {as_of.isoformat()}")
    else:
        state = "streak_broken"
        alerts.append(
            f"no session since {last.isoformat()}; the consecutive-day streak is broken "
            "and must restart from 1"
        )
    if missing and state in {"ok", "missing_today"}:
        alerts.append(f"{len(missing)} past day(s) without events: {[d.isoformat() for d in missing]}")

    return {
        "state": state,
        "first_session_day": first.isoformat(),
        "last_session_day": last.isoformat(),
        "current_streak_days": streak,
        "missing_days": [d.isoformat() for d in missing],
        "alerts": alerts,
    }
