"""Loss-inclusive analytics over verified execution and paper-ledger observations.

P&L is reported at ledger-event and UTC-day level. The current paper ledger does
not prove allocation of realized P&L to individual entry orders, so this module
never invents per-order profit attribution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from research.execution_observations import ExecutionObservationJournal


class PaperOutcomeError(RuntimeError):
    """Learning observations are incomplete, corrupt or not safely interpretable."""


@dataclass(frozen=True)
class DailyPaperOutcome:
    utc_day: str
    ledger_events: int
    order_events: int
    partial_fill_events: int
    close_events: int
    gross_realized_pnl: str
    commission_paid: str
    net_realized_after_commission: str
    max_observed_drawdown_pct: str | None


@dataclass(frozen=True)
class PaperOutcomeReport:
    journal_events: int
    imported_ledger_events: int
    source_ledger_ids: tuple[str, ...]
    order_count: int
    filled_orders: int
    partial_orders: int
    cancelled_orders: int
    open_working_orders: int
    unique_fill_ids: int
    approved_decisions: int
    rejected_decisions: int
    reservation_rejections: int
    broker_submission_errors: int
    close_events: int
    gross_realized_pnl: str
    commission_paid: str
    net_realized_after_commission: str
    max_observed_drawdown_pct: str | None
    drawdown_observations: int
    missing_drawdown_observations: int
    by_utc_day: tuple[DailyPaperOutcome, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_ledger_ids"] = list(self.source_ledger_ids)
        result["by_utc_day"] = [asdict(item) for item in self.by_utc_day]
        result["limitations"] = list(self.limitations)
        return result


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaperOutcomeError(f"invalid {field} in learning observation") from exc
    if not number.is_finite():
        raise PaperOutcomeError(f"non-finite {field} in learning observation")
    return number


def _pages(journal: ExecutionObservationJournal) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = 0
    while True:
        page = journal.list_events(limit=1000, after_seq=cursor)
        if not page:
            break
        events.extend(page)
        cursor = page[-1]["seq"]
        if len(page) < 1000:
            break
    return events


def _drawdown(account: dict[str, Any]) -> Decimal | None:
    balance_value = account.get("balance")
    peak_value = account.get("peak_equity")
    positions = account.get("positions", [])
    marks = account.get("last_prices", {})
    if balance_value is None or peak_value is None:
        return None
    if not isinstance(positions, list) or not isinstance(marks, dict):
        return None
    balance = _decimal(balance_value, "account balance")
    peak = _decimal(peak_value, "peak equity")
    if peak <= 0:
        return None
    unrealized = Decimal("0")
    for position in positions:
        if not isinstance(position, dict):
            return None
        symbol = position.get("symbol")
        if not symbol or symbol not in marks:
            return None
        quantity = _decimal(position.get("quantity"), "position quantity")
        average = _decimal(position.get("average_price"), "position average price")
        mark = _decimal(marks[symbol], "last price")
        unrealized += (mark - average) * quantity
    equity = balance + unrealized
    return max(Decimal("0"), (peak - equity) / peak * Decimal("100"))


def build_paper_outcome_report(
    journal: ExecutionObservationJournal,
) -> PaperOutcomeReport:
    """Build deterministic metrics from a complete, verified journal history."""
    if not journal.verify():
        raise PaperOutcomeError("learning journal hash chain is invalid")
    events = _pages(journal)
    if not journal.verify():
        raise PaperOutcomeError("learning journal changed or became invalid during report generation")

    imported = []
    source_ids: set[str] = set()
    latest_orders: dict[str, dict] = {}
    latest_working: dict[str, dict] = {}
    fill_ids: set[str] = set()
    gross = Decimal("0")
    commission = Decimal("0")
    max_drawdown: Decimal | None = None
    drawdown_observations = 0
    missing_drawdown = 0
    approved = rejected = reservation_rejections = broker_errors = 0
    daily: dict[str, dict[str, Any]] = {}

    for event in events:
        event_type = event["event_type"]
        data = event["data"]
        if event_type == "risk_approved":
            approved += 1
        elif event_type == "risk_rejected":
            rejected += 1
        elif event_type == "reservation_rejected":
            reservation_rejections += 1
        elif event_type == "broker_submission_error":
            broker_errors += 1

        if event_type in {"broker_order_result", "position_close_result"}:
            order_id = data.get("order_id")
            if order_id:
                latest_orders[str(order_id)] = {
                    "order_id": order_id,
                    "client_order_id": data.get("client_order_id"),
                    "symbol": data.get("symbol"),
                    "side": data.get("side"),
                    "quantity": data.get("quantity"),
                    "fill_price": data.get("fill_price"),
                    "status": data.get("result_status") or data.get("status"),
                    "filled_quantity": data.get("filled_quantity"),
                    "remaining_quantity": data.get("remaining_quantity"),
                    "created_at": data.get("created_at"),
                }

        if event_type != "paper_ledger_event":
            continue
        imported.append(event)
        source_id = data.get("source_ledger_id")
        if source_id:
            source_ids.add(str(source_id))
        day = data.get("source_utc_day")
        if not isinstance(day, str) or not day:
            raise PaperOutcomeError("imported ledger event is missing its UTC day")
        day_stats = daily.setdefault(day, {
            "ledger_events": 0, "order_events": 0, "partial_fill_events": 0,
            "close_events": 0, "gross": Decimal("0"), "commission": Decimal("0"),
            "max_drawdown": None,
        })
        day_stats["ledger_events"] += 1
        event_gross = _decimal(data.get("realized_delta"), "realized delta")
        event_commission = _decimal(data.get("commission_delta"), "commission delta")
        gross += event_gross
        commission += event_commission
        day_stats["gross"] += event_gross
        day_stats["commission"] += event_commission

        source_type = data.get("source_event_type")
        if source_type in {"paper_order", "paper_working"}:
            day_stats["order_events"] += 1
        if source_type == "paper_partial_fill":
            day_stats["partial_fill_events"] += 1
        if source_type == "paper_close":
            day_stats["close_events"] += 1

        for order in data.get("orders", []):
            if isinstance(order, dict) and order.get("order_id"):
                latest_orders[str(order["order_id"])] = order
        for order in data.get("working_orders", []):
            if isinstance(order, dict) and order.get("order_id"):
                latest_working[str(order["order_id"])] = order
        for fill_id in data.get("fill_results", {}):
            fill_ids.add(str(fill_id))

        account = data.get("account_snapshot")
        if isinstance(account, dict):
            drawdown = _drawdown(account)
            if drawdown is None:
                missing_drawdown += 1
            else:
                drawdown_observations += 1
                max_drawdown = drawdown if max_drawdown is None else max(max_drawdown, drawdown)
                current_day_max = day_stats["max_drawdown"]
                day_stats["max_drawdown"] = (
                    drawdown if current_day_max is None else max(current_day_max, drawdown)
                )
        else:
            missing_drawdown += 1

    gross_net = gross - commission
    orders = dict(latest_orders)
    for order_id, order in latest_working.items():
        orders.setdefault(order_id, order)
    statuses = [str(order.get("status", "")).lower() for order in orders.values()]
    filled = sum(status == "filled" for status in statuses)
    cancelled = sum(status == "cancelled" for status in statuses)
    partial = sum(
        status == "partial"
        or (
            status not in {"filled", "cancelled"}
            and _decimal(order.get("filled_quantity", "0"), "filled quantity") > 0
        )
        for order, status in zip(orders.values(), statuses)
    )
    open_working = sum(status in {"open", "partial"} for status in statuses)
    close_count = sum(day["close_events"] for day in daily.values())

    daily_reports = tuple(
        DailyPaperOutcome(
            utc_day=day,
            ledger_events=stats["ledger_events"],
            order_events=stats["order_events"],
            partial_fill_events=stats["partial_fill_events"],
            close_events=stats["close_events"],
            gross_realized_pnl=str(stats["gross"]),
            commission_paid=str(stats["commission"]),
            net_realized_after_commission=str(stats["gross"] - stats["commission"]),
            max_observed_drawdown_pct=(
                str(stats["max_drawdown"]) if stats["max_drawdown"] is not None else None
            ),
        )
        for day, stats in sorted(daily.items())
    )

    return PaperOutcomeReport(
        journal_events=len(events),
        imported_ledger_events=len(imported),
        source_ledger_ids=tuple(sorted(source_ids)),
        order_count=len(orders),
        filled_orders=filled,
        partial_orders=partial,
        cancelled_orders=cancelled,
        open_working_orders=open_working,
        unique_fill_ids=len(fill_ids),
        approved_decisions=approved,
        rejected_decisions=rejected,
        reservation_rejections=reservation_rejections,
        broker_submission_errors=broker_errors,
        close_events=close_count,
        gross_realized_pnl=str(gross),
        commission_paid=str(commission),
        net_realized_after_commission=str(gross_net),
        max_observed_drawdown_pct=(
            str(max_drawdown) if max_drawdown is not None else None
        ),
        drawdown_observations=drawdown_observations,
        missing_drawdown_observations=missing_drawdown,
        by_utc_day=daily_reports,
        limitations=(
            "Realized P&L and commission are attributed to source ledger events and UTC days, not individual entry orders.",
            "Missing quote, strategy, experiment or account metadata remains unknown; no values are inferred.",
            "This report is descriptive only and cannot approve, deploy or promote a strategy.",
        ),
    )
