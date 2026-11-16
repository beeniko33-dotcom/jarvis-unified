"""Independent replay of a JSONL paper ledger against its own recorded balances.

The paper broker writes cumulative balance, realized P&L, commission and open-position
count on every fill row. This module replays the fills from scratch with the same
accounting rules and reports any row where the recorded figures disagree. It reads the
ledger only; it never touches a broker, network or credentials.

Scope and limits (stated so a clean result is not over-read):
- Exact for immediate full fills. Rows that belong to working or partially filled orders
  record cumulative quantity and average price, so incremental fills cannot be recovered
  exactly; they are reported as unsupported and the result is "incomplete", never "reconciled".
- The starting balance is not stored in the ledger. It is derived from the first row, so the
  first row's balance is not an independent check; every later row is.
- Equity is not replayed because marks are not recorded in the ledger.
- A match proves internal consistency of the ledger, not market-data authenticity.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_ZERO = Decimal("0")
_CHECKED_FIELDS = ("realized_pnl", "commission_paid", "balance", "open_positions", "commission")


def _dec(row: dict, key: str) -> Decimal:
    try:
        value = Decimal(str(row[key]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError(f"row lacks a valid {key}") from exc
    if not value.is_finite():
        raise ValueError(f"{key} must be finite")
    return value


def _safe_dec(row: dict, key: str) -> Decimal:
    try:
        return _dec(row, key)
    except ValueError:
        return _ZERO


def _is_full_immediate_fill(row: dict) -> bool:
    if row.get("fill_id") is not None:
        return False
    if row.get("status") != "filled":
        return False
    remaining = row.get("remaining_quantity")
    if remaining is not None and Decimal(str(remaining)) != _ZERO:
        return False
    quantity = row.get("quantity")
    filled = row.get("filled_quantity")
    return quantity is not None and filled is not None and Decimal(str(quantity)) == Decimal(str(filled))


def reconcile_ledger(rows: list[dict]) -> dict[str, Any]:
    """Replay ``rows`` and return discrepancies, unsupported rows and an overall status."""
    if not rows:
        raise ValueError("ledger has no rows")

    positions: dict[str, tuple[Decimal, Decimal]] = {}  # symbol -> (signed qty, avg price)
    realized = _ZERO
    commission_total = _ZERO
    balance: Decimal | None = None
    discrepancies: list[dict[str, str | int]] = []
    unsupported: list[dict[str, str | int]] = []

    def flag(index: int, field: str, ledger: Decimal | int, replayed: Decimal | int) -> None:
        discrepancies.append(
            {"row": index, "field": field, "ledger": str(ledger), "replayed": str(replayed)}
        )

    for index, row in enumerate(rows, 1):
        if not _is_full_immediate_fill(row):
            unsupported.append(
                {"row": index, "reason": "working or partially filled order; incremental fill not recoverable"}
            )
            # State can no longer be trusted after an unreplayable fill.
            balance = None
            break

        symbol = str(row["symbol"]).strip().upper()
        quantity = _dec(row, "filled_quantity")
        price = _dec(row, "fill_price")
        commission = _dec(row, "commission")
        signed = quantity if row["side"] == "buy" else -quantity
        current = positions.get(symbol)
        pnl = _ZERO

        if current and current[0] * signed < 0:
            current_qty, avg = current
            closing = min(abs(current_qty), quantity)
            direction = Decimal("1") if current_qty > 0 else Decimal("-1")
            pnl = (price - avg) * closing * direction
            realized += pnl
            commission_total += commission
            remaining = current_qty + direction * -closing
            if remaining == 0:
                positions.pop(symbol, None)
            else:
                positions[symbol] = (remaining, avg)
            excess = quantity - closing
            if excess > 0:
                positions[symbol] = ((Decimal("1") if signed > 0 else Decimal("-1")) * excess, price)
            net_change = pnl - commission
        elif current:
            current_qty, avg = current
            total = abs(current_qty) + quantity
            positions[symbol] = (current_qty + signed, (abs(current_qty) * avg + quantity * price) / total)
            commission_total += commission
            net_change = -commission
        else:
            positions[symbol] = (signed, price)
            commission_total += commission
            net_change = -commission

        if balance is None:
            # Derive the starting balance from the first row (not an independent check).
            balance = _dec(row, "balance") - net_change
        balance += net_change

        expected = {
            "realized_pnl": realized,
            "commission_paid": commission_total,
            "balance": balance,
            "open_positions": len(positions),
        }
        for field, replayed in expected.items():
            ledger_value = _dec(row, field)
            if ledger_value != replayed:
                flag(index, field, ledger_value, replayed)

        previous = _dec(rows[index - 2], "commission_paid") if index > 1 else _ZERO
        if _dec(row, "commission_paid") - previous != commission:
            flag(index, "commission", commission, _dec(row, "commission_paid") - previous)

    # Commission is never negative, so cumulative commission_paid only falls when a new
    # broker instance started appending to the same file. Report it as the likely cause
    # of any discrepancy; do not silently split the ledger into separate accounts.
    boundaries = [
        index
        for index in range(2, len(rows) + 1)
        if _safe_dec(rows[index - 1], "commission_paid") < _safe_dec(rows[index - 2], "commission_paid")
    ]

    if unsupported:
        status = "incomplete"
    elif discrepancies:
        status = "discrepancies"
    else:
        status = "reconciled"

    return {
        "status": status,
        "rows_in_ledger": len(rows),
        "rows_replayed": len(rows) if not unsupported else unsupported[0]["row"] - 1,
        "discrepancies": discrepancies,
        "unsupported_rows": unsupported,
        "suspected_session_boundaries": boundaries,
        "boundary_note": (
            "Cumulative commission_paid fell at these rows, which means a new broker instance "
            "appended to this file. Such a ledger is not one continuous account and cannot be "
            "replayed as one; use a fresh ledger per session or the persistent broker."
            if boundaries else None
        ),
        "replayed_open_positions": {sym: str(qty) for sym, (qty, _avg) in sorted(positions.items())},
        "note": (
            "Internal consistency only: a match is not proof of market-data authenticity, "
            "and equity is not replayed because marks are not recorded."
        ),
    }
