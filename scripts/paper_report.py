#!/usr/bin/env python3
"""Summarize Jarvis paper audit ledgers; never connects to a broker."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

# Allow `python scripts/paper_report.py` from the repo root to import `research`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"line {line_no} must contain a JSON object")
            required = {"ts", "status", "realized_pnl", "commission_paid", "equity", "balance", "open_positions"}
            missing = required.difference(row)
            if missing:
                raise ValueError(
                    f"line {line_no} lacks {', '.join(sorted(missing))}; "
                    "use a ledger written by the Level 3-enabled paper broker"
                )
            try:
                _utc_timestamp(row["ts"])
                for field in ("realized_pnl", "equity", "balance", "commission_paid"):
                    value = Decimal(str(row[field]))
                    if not value.is_finite():
                        raise ValueError(f"{field} must be finite")
                positions = row["open_positions"]
                if isinstance(positions, bool) or int(positions) != positions or int(positions) < 0:
                    raise ValueError("open_positions must be a non-negative integer")
                slippage_fields = {"raw_price", "fill_price", "side", "quantity"}
                present_slippage_fields = slippage_fields.intersection(row)
                if present_slippage_fields and present_slippage_fields != slippage_fields:
                    raise ValueError("slippage audit fields must be provided together")
                if present_slippage_fields:
                    raw_price = Decimal(str(row["raw_price"]))
                    fill_price = Decimal(str(row["fill_price"]))
                    quantity = Decimal(str(row["quantity"]))
                    if (
                        not raw_price.is_finite()
                        or not fill_price.is_finite()
                        or not quantity.is_finite()
                        or raw_price <= 0
                        or fill_price <= 0
                        or quantity <= 0
                        or row["side"] not in {"buy", "sell"}
                    ):
                        raise ValueError("invalid slippage audit values")
            except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
                raise ValueError(f"invalid audit values on line {line_no}") from exc
            rows.append(row)
    return rows


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def decision_stats(events: list[dict]) -> dict:
    """Count entry decisions from execution-observation events.

    The rate is rejected entries over decided entries (risk_approved + risk_rejected).
    A reservation rejection happens after a risk approval, so it adds to the rejected
    count without adding to the denominator.
    """
    counts = {"risk_approved": 0, "risk_rejected": 0, "reservation_rejected": 0, "broker_submission_error": 0}
    for event in events:
        kind = event.get("event_type")
        if kind in counts:
            counts[kind] += 1
    decided = counts["risk_approved"] + counts["risk_rejected"]
    rejected = counts["risk_rejected"] + counts["reservation_rejected"]
    return {
        "decided_entries": decided,
        "rejected_entries": rejected,
        "broker_submission_errors": counts["broker_submission_error"],
        "rejected_entry_rate": str(Decimal(rejected) / Decimal(decided)) if decided else None,
    }


def _rejection_fields(decisions: list[dict] | None) -> dict:
    if decisions is None:
        return {
            "rejected_entry_rate": None,
            "rejected_entry_rate_note": (
                "Unavailable: this fill-only ledger does not record risk-rejected entries; "
                "pass --observations-db to include them."
            ),
        }
    stats = decision_stats(decisions)
    if stats["rejected_entry_rate"] is None:
        stats["rejected_entry_rate_note"] = (
            "No entry decisions were recorded in the observations journal."
        )
    return stats


def summarize(rows: list[dict], decisions: list[dict] | None = None) -> dict:
    if not rows:
        raise ValueError("ledger contains no filled-order records")

    timestamps = [_utc_timestamp(row["ts"]) for row in rows]
    if any(current < previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("ledger timestamps are out of order")

    realized_deltas: list[Decimal] = []
    previous_realized = Decimal("0")
    for row in rows:
        current = Decimal(str(row["realized_pnl"]))
        delta = current - previous_realized
        if delta:
            realized_deltas.append(delta)
        previous_realized = current

    equities = [Decimal(str(row["equity"])) for row in rows]
    peak = equities[0]
    max_drawdown = Decimal("0")
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    wins = [value for value in realized_deltas if value > 0]
    losses = [value for value in realized_deltas if value < 0]
    total_realized = previous_realized
    avg = (
        sum(realized_deltas, Decimal("0")) / len(realized_deltas)
        if realized_deltas else Decimal("0")
    )
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = -sum(losses, Decimal("0"))
    profit_factor = (
        str(gross_profit / gross_loss) if gross_loss else None
    )
    session_days = sorted({timestamp.date() for timestamp in timestamps})
    longest_streak = 0
    current_streak = 0
    previous_day = None
    for day in session_days:
        current_streak = (
            current_streak + 1
            if previous_day is not None and (day - previous_day).days == 1
            else 1
        )
        longest_streak = max(longest_streak, current_streak)
        previous_day = day

    slippage_rows = [row for row in rows if "raw_price" in row]
    slippage_cost = Decimal("0")
    slippage_notional = Decimal("0")
    for row in slippage_rows:
        raw_price = Decimal(str(row["raw_price"]))
        fill_price = Decimal(str(row["fill_price"]))
        quantity = Decimal(str(row["quantity"]))
        adverse_difference = fill_price - raw_price
        if row["side"] == "sell":
            adverse_difference = -adverse_difference
        slippage_cost += adverse_difference * quantity
        slippage_notional += raw_price * quantity
    slippage_bps = (
        str(slippage_cost / slippage_notional * Decimal("10000"))
        if slippage_notional else None
    )
    attributed_fill_count = sum(
        all(row.get(field) for field in ("strategy_id", "strategy_version", "quote_source"))
        for row in rows
    )

    return {
        "ledger_rows": len(rows),
        "session_days": [day.isoformat() for day in session_days],
        "distinct_session_days": len(session_days),
        "consecutive_session_days": longest_streak,
        "calendar_span_days": (session_days[-1] - session_days[0]).days + 1,
        "days_without_ledger_events": (session_days[-1] - session_days[0]).days + 1 - len(session_days),
        "realized_trade_events": len(realized_deltas),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": str(Decimal(len(wins)) / len(realized_deltas)) if realized_deltas else None,
        "expectancy_per_realized_event": str(avg),
        "total_realized_pnl_before_commission": str(total_realized),
        "total_commission_paid": str(rows[-1]["commission_paid"]),
        "net_realized_pnl_after_commission": str(total_realized - Decimal(str(rows[-1]["commission_paid"]))),
        "gross_profit": str(gross_profit),
        "gross_loss": str(gross_loss),
        "profit_factor": profit_factor,
        "max_equity_drawdown": str(max_drawdown),
        "slippage_observations": len(slippage_rows),
        "net_slippage_cost": str(slippage_cost) if slippage_rows else None,
        "notional_weighted_slippage_bps": slippage_bps,
        "attributed_fill_count": attributed_fill_count,
        "attribution_coverage": str(Decimal(attributed_fill_count) / len(rows)),
        **_rejection_fields(decisions),
        "ending_balance": str(rows[-1]["balance"]),
        "ending_equity": str(rows[-1]["equity"]),
        "open_positions_at_end": int(rows[-1]["open_positions"]),
        "validation_note": (
            "Descriptive paper results only; not a forecast, guarantee, or live-trading approval."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?", default=Path("var/paper_ledger.jsonl"))
    parser.add_argument(
        "--min-days",
        type=int,
        default=1,
        help="fail unless the ledger has this many consecutive UTC calendar days with events",
    )
    parser.add_argument(
        "--observations-db",
        type=Path,
        default=None,
        help="execution-observation journal written by paper_session.py; enables rejected-entry rate",
    )
    args = parser.parse_args(argv)
    if args.min_days < 1:
        parser.error("--min-days must be at least 1")
    if not args.ledger.is_file():
        parser.error(f"ledger not found: {args.ledger}")
    decisions = None
    if args.observations_db is not None:
        if not args.observations_db.is_file():
            parser.error(f"observations journal not found: {args.observations_db}")
        from research.execution_observations import ExecutionObservationJournal

        journal = ExecutionObservationJournal(args.observations_db)
        if not journal.verify():
            parser.error("observations journal failed hash-chain verification; refusing to report")
        decisions = journal.list_events(limit=10000)
    try:
        result = summarize(load_rows(args.ledger), decisions)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if result["consecutive_session_days"] < args.min_days:
        print(
            f"NOT VALIDATED: need {args.min_days} consecutive UTC days with ledger events; "
            f"longest run is {result['consecutive_session_days']} days.",
        )
        return 2
    if result["open_positions_at_end"] != 0:
        print("NOT VALIDATED: close or explicitly account for all open paper positions.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
