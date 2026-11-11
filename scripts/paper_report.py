#!/usr/bin/env python3
"""Summarize Jarvis paper audit ledgers; never connects to a broker."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


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
            required = {"ts", "status", "realized_pnl", "commission_paid", "equity", "balance", "open_positions"}
            missing = required.difference(row)
            if missing:
                raise ValueError(
                    f"line {line_no} lacks {', '.join(sorted(missing))}; "
                    "use a ledger written by the Level 3-enabled paper broker"
                )
            try:
                datetime.fromisoformat(row["ts"])
                Decimal(str(row["realized_pnl"]))
                Decimal(str(row["equity"]))
                Decimal(str(row["balance"]))
                Decimal(str(row["commission_paid"]))
            except (TypeError, ValueError, InvalidOperation) as exc:
                raise ValueError(f"invalid audit values on line {line_no}") from exc
            rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("ledger contains no filled-order records")
    rows.sort(key=lambda row: row["ts"])
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
    session_days = sorted({datetime.fromisoformat(row["ts"]).date().isoformat() for row in rows})
    return {
        "ledger_rows": len(rows),
        "session_days": session_days,
        "distinct_session_days": len(session_days),
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
        "ending_balance": str(rows[-1]["balance"]),
        "ending_equity": str(rows[-1]["equity"]),
        "open_positions_at_end": int(rows[-1]["open_positions"]),
        "validation_note": (
            "Descriptive paper results only; not a forecast, guarantee, or live-trading approval."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?", default=Path("var/paper_ledger.jsonl"))
    parser.add_argument("--min-days", type=int, default=1,
                        help="fail unless the ledger spans at least this many UTC calendar days")
    args = parser.parse_args()
    if args.min_days < 1:
        parser.error("--min-days must be at least 1")
    if not args.ledger.is_file():
        parser.error(f"ledger not found: {args.ledger}")
    try:
        result = summarize(load_rows(args.ledger))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if result["distinct_session_days"] < args.min_days:
        print(
            f"NOT VALIDATED: need {args.min_days} distinct UTC days; "
            f"found {result['distinct_session_days']}.",
        )
        return 2
    if result["open_positions_at_end"] != 0:
        print("NOT VALIDATED: close or explicitly account for all open paper positions.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
