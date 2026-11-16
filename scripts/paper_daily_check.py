#!/usr/bin/env python3
"""Daily paper-validation check: missing sessions, streak health, ledger and journal integrity.

Read-only; never connects to a broker. Designed to be run once per UTC day by an operator's
own scheduler. It reports; it never repairs, backfills or manufactures observations.

Exit codes: 0 healthy, 2 anything needing operator attention.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.ledger_reconciliation import reconcile_ledger  # noqa: E402
from scripts.paper_report import _utc_timestamp, load_rows  # noqa: E402


def check(
    rows: list[dict],
    *,
    as_of: date,
    journal_ok: bool | None = None,
) -> dict:
    """Assess a ledger as of a UTC date. Pure function: no clock, no I/O."""
    days = sorted({_utc_timestamp(row["ts"]).date() for row in rows})
    last_day = days[-1]
    first_day = days[0]
    expected = {first_day + timedelta(days=i) for i in range((as_of - first_day).days + 1)}
    missing = sorted(expected - set(days))

    # Current streak: consecutive session days ending at the most recent session day.
    streak = 1
    for previous, current in zip(reversed(days[:-1]), reversed(days[1:])):
        if (current - previous).days == 1:
            streak += 1
        else:
            break

    alerts: list[str] = []
    if last_day > as_of:
        alerts.append(f"ledger contains events dated after {as_of.isoformat()}")
        state = "future_dated"
    elif last_day == as_of:
        state = "ok"
    elif last_day == as_of - timedelta(days=1):
        state = "missing_today"
        alerts.append(f"no session recorded yet for {as_of.isoformat()}")
    else:
        state = "streak_broken"
        alerts.append(
            f"no session since {last_day.isoformat()}; the consecutive-day streak is broken "
            f"and must restart from 1"
        )
    if missing and state in {"ok", "missing_today"}:
        alerts.append(f"{len(missing)} past day(s) without events: {[d.isoformat() for d in missing]}")

    reconciliation = reconcile_ledger(rows)
    if reconciliation["status"] != "reconciled":
        alerts.append(f"ledger reconciliation status is {reconciliation['status']}")
    if journal_ok is False:
        alerts.append("observations journal failed hash-chain verification")
    open_positions = int(rows[-1]["open_positions"])
    if open_positions:
        alerts.append(f"{open_positions} paper position(s) still open at end of ledger")

    healthy = state == "ok" and not missing and not alerts
    return {
        "as_of_utc_date": as_of.isoformat(),
        "state": state,
        "healthy": healthy,
        "first_session_day": first_day.isoformat(),
        "last_session_day": last_day.isoformat(),
        "current_streak_days": streak,
        "streak_counts_toward_level_3": False,
        "streak_note": (
            "Informational only. Level 3 additionally requires licensed market-data provenance, "
            "per-decision attribution and independent review; ledger days alone do not qualify."
        ),
        "missing_days": [d.isoformat() for d in missing],
        "reconciliation_status": reconciliation["status"],
        "observations_journal_verified": journal_ok,
        "open_positions_at_end": open_positions,
        "alerts": alerts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?", default=Path("var/paper_ledger.jsonl"))
    parser.add_argument("--observations-db", type=Path, default=None)
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="UTC date to assess (YYYY-MM-DD); defaults to today in UTC",
    )
    args = parser.parse_args(argv)
    if not args.ledger.is_file():
        parser.error(f"ledger not found: {args.ledger}")
    as_of = args.as_of or datetime.now(timezone.utc).date()

    journal_ok = None
    if args.observations_db is not None:
        if not args.observations_db.is_file():
            parser.error(f"observations journal not found: {args.observations_db}")
        from research.execution_observations import ExecutionObservationJournal

        journal_ok = ExecutionObservationJournal(args.observations_db).verify()
    try:
        result = check(load_rows(args.ledger), as_of=as_of, journal_ok=journal_ok)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0 if result["healthy"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
