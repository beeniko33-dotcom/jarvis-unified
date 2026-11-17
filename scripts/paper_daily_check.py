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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.day_coverage import assess_days  # noqa: E402
from research.ledger_reconciliation import reconcile_ledger  # noqa: E402
from scripts.paper_report import _utc_timestamp, load_rows  # noqa: E402


def check(
    rows: list[dict],
    *,
    as_of: date,
    journal_ok: bool | None = None,
) -> dict:
    """Assess a ledger as of a UTC date. Pure function: no clock, no I/O."""
    coverage = assess_days([_utc_timestamp(row["ts"]).date() for row in rows], as_of)
    state = coverage["state"]
    missing = coverage["missing_days"]
    alerts: list[str] = list(coverage["alerts"])

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
        "first_session_day": coverage["first_session_day"],
        "last_session_day": coverage["last_session_day"],
        "current_streak_days": coverage["current_streak_days"],
        "streak_counts_toward_level_3": False,
        "streak_note": (
            "Informational only. Level 3 additionally requires licensed market-data provenance, "
            "per-decision attribution and independent review; ledger days alone do not qualify."
        ),
        "missing_days": missing,
        "reconciliation_status": reconciliation["status"],
        "observations_journal_verified": journal_ok,
        "open_positions_at_end": open_positions,
        "alerts": alerts,
    }


def check_account(audit: dict, *, as_of: date) -> dict:
    """Turn a full-history account audit into a daily verdict. Any error or warning is unhealthy."""
    attention = [item for item in audit["findings"] if item["severity"] in {"error", "warning"}]
    coverage = audit["trading_day_coverage"]
    healthy = audit["status"] == "verified" and not attention and coverage is not None \
        and coverage["state"] == "ok"
    return {
        "mode": "persistent_account",
        "as_of_utc_date": as_of.isoformat(),
        "healthy": healthy,
        "status": audit["status"],
        "account_id": audit["account_id"],
        "events": audit["events"],
        "state": coverage["state"] if coverage else None,
        "current_streak_days": coverage["current_streak_days"] if coverage else 0,
        "streak_counts_toward_level_3": False,
        "open_positions_at_end": audit["open_positions_at_end"],
        "alerts": [item["message"] for item in attention],
        "findings": attention,
        "counts_toward_level_3": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?", default=Path("var/paper_ledger.jsonl"))
    parser.add_argument("--observations-db", type=Path, default=None)
    parser.add_argument(
        "--account-db",
        type=Path,
        default=None,
        help="check a persistent SQLite account (paper_session.py --account-db) over its full "
        "history instead of a JSONL ledger",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="UTC date to assess (YYYY-MM-DD); defaults to today in UTC",
    )
    args = parser.parse_args(argv)
    as_of = args.as_of or datetime.now(timezone.utc).date()

    if args.account_db is not None:
        from research.persistent_account_audit import audit_account

        try:
            result = check_account(audit_account(args.account_db, as_of=as_of), as_of=as_of)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return 0 if result["healthy"] else 2

    if not args.ledger.is_file():
        parser.error(f"ledger not found: {args.ledger}")

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
