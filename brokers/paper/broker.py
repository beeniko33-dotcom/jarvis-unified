"""Deterministic in-memory paper broker with optional audit ledger; no network or real-money execution."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import uuid4

from core.models import AccountSnapshot, OrderRequest, OrderResult, OrderStatus, Position, Side


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_LINEAGE_KEYS = frozenset({
    "strategy_id", "strategy_version", "strategy_config_hash", "experiment_id",
    "signal_id", "signal_type", "signal_context_hash", "data_source_id", "data_hash",
    "quote_source", "quote_timestamp",
})
_SECRET_MARKERS = ("secret", "password", "token", "private_key", "api_key", "authorization", "bearer")


def _paper_metadata(metadata: dict) -> dict:
    """Persist only bounded, non-secret research lineage; never arbitrary metadata."""
    lineage = metadata.get("research_lineage") if isinstance(metadata, dict) else None
    if not isinstance(lineage, dict):
        return {}
    safe = {}
    for key, value in lineage.items():
        if key not in _LINEAGE_KEYS or not isinstance(value, str):
            continue
        value = value.strip()
        lowered = value.lower()
        if not value or len(value) > 128 or any(marker in lowered for marker in _SECRET_MARKERS):
            continue
        if key in {"strategy_config_hash", "signal_context_hash", "data_hash"}:
            if not (len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)):
                continue
        elif key == "quote_timestamp":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                continue
        elif not all(ch.isalnum() or ch in "_-.:/" for ch in value):
            continue
        safe[key] = value
    return {"research_lineage": safe} if safe else {}


@dataclass
class WorkingOrder:
    order_id: str
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    limit_price: Decimal
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal = Decimal("0")
    status: str = OrderStatus.OPEN.value
    created_at: datetime = field(default_factory=_utc_now)
    applied_fill_ids: set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity


class PaperBroker:
    """Paper execution adapter with optional working-order / partial-fill simulation."""

    def __init__(
        self,
        starting_balance: Decimal = Decimal("10000"),
        *,
        commission_per_side: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
        ledger_path: str | Path | None = None,
    ) -> None:
        if starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        if commission_per_side < 0 or not commission_per_side.is_finite():
            raise ValueError("commission_per_side must be finite and non-negative")
        if slippage_bps < 0 or not slippage_bps.is_finite():
            raise ValueError("slippage_bps must be finite and non-negative")

        self._balance = Decimal(starting_balance)
        self._realized_pnl = Decimal("0")
        self._commission_paid = Decimal("0")
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        self._client_ids: dict[str, OrderResult] = {}
        self._client_requests: dict[str, tuple[str, Side, Decimal, Decimal]] = {}
        self._working: dict[str, WorkingOrder] = {}
        # fill_id -> (order_id, OrderResult) so cross-order reuse is rejected
        self._fill_results: dict[str, tuple[str, OrderResult]] = {}
        self._last_prices: dict[str, Decimal] = {}
        self._commission_per_side = Decimal(commission_per_side)
        self._slippage_bps = Decimal(slippage_bps)
        self._ledger_path = Path(ledger_path) if ledger_path else None
        self._lock = RLock()

        if self._ledger_path is not None:
            self._ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def _apply_slippage(self, side: Side, price: Decimal) -> Decimal:
        if self._slippage_bps == 0:
            return price
        factor = self._slippage_bps / Decimal("10000")
        if side == Side.BUY:
            return price * (Decimal("1") + factor)
        return price * (Decimal("1") - factor)

    def _append_ledger(
        self,
        result: OrderResult,
        raw_price: Decimal,
        fill_price: Decimal,
        commission: Decimal,
        *,
        fill_id: str | None = None,
    ) -> None:
        if self._ledger_path is None:
            return
        record = {
            "ts": _utc_now().isoformat(),
            "order_id": result.order_id,
            "client_order_id": result.client_order_id,
            "symbol": result.symbol,
            "side": result.side.value,
            "quantity": str(result.quantity),
            "filled_quantity": str(result.filled_quantity or result.quantity),
            "remaining_quantity": str(result.remaining_quantity or Decimal("0")),
            "raw_price": str(raw_price),
            "fill_price": str(fill_price),
            "commission": str(commission),
            "status": result.status,
            "fill_id": fill_id,
            "balance": str(self._balance),
            "equity": str(self.get_account().equity),
            "realized_pnl": str(self._realized_pnl),
            "commission_paid": str(self._commission_paid),
            "open_positions": len(self._positions),
        }
        with self._ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _apply_fill_to_position(
        self, symbol: str, side: Side, quantity: Decimal, fill_price: Decimal
    ) -> Decimal:
        commission = self._commission_per_side
        current = self._positions.get(symbol)
        signed = quantity if side == Side.BUY else -quantity

        if current and current.quantity * signed < 0:
            closing = min(abs(current.quantity), quantity)
            direction = Decimal("1") if current.quantity > 0 else Decimal("-1")
            pnl = (fill_price - current.average_price) * closing * direction
            self._realized_pnl += pnl
            self._balance += pnl - commission
            self._commission_paid += commission

            remaining = current.quantity + direction * -closing
            if remaining == 0:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = Position(
                    symbol, remaining, current.average_price, current.opened_at
                )

            excess = quantity - closing
            if excess > 0:
                new_signed = (Decimal("1") if signed > 0 else Decimal("-1")) * excess
                self._positions[symbol] = Position(symbol, new_signed, fill_price)
        elif current:
            total = abs(current.quantity) + quantity
            avg = (
                abs(current.quantity) * current.average_price + quantity * fill_price
            ) / total
            self._positions[symbol] = Position(
                symbol, current.quantity + signed, avg, current.opened_at
            )
            self._balance -= commission
            self._commission_paid += commission
        else:
            self._positions[symbol] = Position(symbol, signed, fill_price)
            self._balance -= commission
            self._commission_paid += commission

        self._last_prices[symbol] = fill_price
        return commission

    def set_last_price(self, symbol: str, price: Decimal | float | str) -> None:
        p = Decimal(str(price))
        if not p.is_finite() or p <= 0:
            raise ValueError("price must be finite and positive")
        with self._lock:
            self._last_prices[symbol.strip().upper()] = p

    def set_last_prices(self, prices: dict[str, Decimal | float | str]) -> None:
        for symbol, price in prices.items():
            self.set_last_price(symbol, price)

    def place_order(self, order: OrderRequest) -> OrderResult:
        if not order.symbol.strip():
            raise ValueError("symbol is required")
        if not isinstance(order.side, Side):
            raise ValueError("unsupported order side")
        if (
            not order.quantity.is_finite()
            or not order.price.is_finite()
            or order.quantity <= 0
            or order.price <= 0
        ):
            raise ValueError("quantity and price must be finite and positive")
        if not order.client_order_id.strip():
            raise ValueError("client_order_id is required")

        symbol = order.symbol.strip().upper()
        with self._lock:
            if order.client_order_id in self._client_ids:
                prior = self._client_ids[order.client_order_id]
                fingerprint = self._client_requests[order.client_order_id]
                same_request = fingerprint == (symbol, order.side, order.quantity, order.price)
                if not same_request:
                    raise ValueError("client_order_id was already used for a different order")
                return prior

            # A partially-filled working order is still active and is not yet
            # present in _client_ids. Treat a retry with the same client ID as
            # an idempotent lookup, never as a second executable order.
            for working in self._working.values():
                if working.client_order_id != order.client_order_id:
                    continue
                same_request = (
                    working.symbol,
                    working.side,
                    working.quantity,
                    working.limit_price,
                ) == (symbol, order.side, order.quantity, order.price)
                if not same_request:
                    raise ValueError(
                        "client_order_id was already used for a different order"
                    )
                return self._orders[working.order_id]

            raw_price = order.price
            fill_price = self._apply_slippage(order.side, raw_price)
            commission = self._apply_fill_to_position(symbol, order.side, order.quantity, fill_price)

            result = OrderResult(
                str(uuid4()),
                order.client_order_id,
                symbol,
                order.side,
                order.quantity,
                fill_price,
                OrderStatus.FILLED.value,
                filled_quantity=order.quantity,
                remaining_quantity=Decimal("0"),
                metadata=_paper_metadata(order.metadata),
            )
            self._orders[result.order_id] = result
            self._client_ids[order.client_order_id] = result
            self._client_requests[order.client_order_id] = (
                symbol,
                order.side,
                order.quantity,
                order.price,
            )
            self._append_ledger(result, raw_price, fill_price, commission)
            return result

    def place_working_order(self, order: OrderRequest) -> OrderResult:
        if not order.symbol.strip():
            raise ValueError("symbol is required")
        if not isinstance(order.side, Side):
            raise ValueError("unsupported order side")
        if (
            not order.quantity.is_finite()
            or not order.price.is_finite()
            or order.quantity <= 0
            or order.price <= 0
        ):
            raise ValueError("quantity and price must be finite and positive")
        if not order.client_order_id.strip():
            raise ValueError("client_order_id is required")

        symbol = order.symbol.strip().upper()
        with self._lock:
            if order.client_order_id in self._client_ids or order.client_order_id in {
                w.client_order_id for w in self._working.values()
            }:
                raise ValueError("client_order_id already in use")

            order_id = str(uuid4())
            working = WorkingOrder(
                order_id=order_id,
                client_order_id=order.client_order_id,
                symbol=symbol,
                side=order.side,
                quantity=order.quantity,
                limit_price=order.price,
                metadata=_paper_metadata(order.metadata),
            )
            self._working[order_id] = working
            result = OrderResult(
                order_id,
                order.client_order_id,
                symbol,
                order.side,
                order.quantity,
                Decimal("0"),
                OrderStatus.OPEN.value,
                filled_quantity=Decimal("0"),
                remaining_quantity=order.quantity,
                metadata=_paper_metadata(order.metadata),
            )
            self._orders[order_id] = result
            return result

    def apply_partial_fill(
        self,
        order_id: str,
        fill_quantity: Decimal,
        price: Decimal | float | str | None = None,
        *,
        fill_id: str | None = None,
    ) -> OrderResult:
        """Apply a partial or completing fill. fill_id is scoped to order_id."""
        fill_quantity = Decimal(str(fill_quantity))
        if not fill_quantity.is_finite() or fill_quantity <= 0:
            raise ValueError("fill_quantity must be finite and positive")
        if fill_id is not None and not str(fill_id).strip():
            raise ValueError("fill_id must be non-empty when provided")

        with self._lock:
            if fill_id is not None and fill_id in self._fill_results:
                prior_order_id, prior_result = self._fill_results[fill_id]
                if prior_order_id != order_id:
                    raise ValueError(
                        f"fill_id {fill_id!r} was already applied to a different order"
                    )
                return prior_result

            working = self._working.get(order_id)
            if working is None:
                raise ValueError(f"no working order {order_id}")
            if working.status in {OrderStatus.FILLED.value, OrderStatus.CANCELLED.value}:
                raise ValueError(f"order {order_id} is {working.status}")
            if fill_id is not None and fill_id in working.applied_fill_ids:
                return self._orders[order_id]
            if fill_quantity > working.remaining_quantity:
                raise ValueError("fill_quantity exceeds remaining quantity")

            raw_price = Decimal(str(price)) if price is not None else working.limit_price
            if not raw_price.is_finite() or raw_price <= 0:
                raise ValueError("fill price must be finite and positive")
            fill_price = self._apply_slippage(working.side, raw_price)
            commission = self._apply_fill_to_position(
                working.symbol, working.side, fill_quantity, fill_price
            )

            prior_filled = working.filled_quantity
            new_filled = prior_filled + fill_quantity
            if prior_filled == 0:
                working.average_fill_price = fill_price
            else:
                working.average_fill_price = (
                    working.average_fill_price * prior_filled + fill_price * fill_quantity
                ) / new_filled
            working.filled_quantity = new_filled
            if fill_id is not None:
                working.applied_fill_ids.add(fill_id)
            if working.remaining_quantity == 0:
                working.status = OrderStatus.FILLED.value
            else:
                working.status = OrderStatus.PARTIAL.value

            result = OrderResult(
                working.order_id,
                working.client_order_id,
                working.symbol,
                working.side,
                working.quantity,
                working.average_fill_price,
                working.status,
                filled_quantity=working.filled_quantity,
                remaining_quantity=working.remaining_quantity,
                metadata=dict(working.metadata),
            )
            self._orders[order_id] = result
            if fill_id is not None:
                self._fill_results[fill_id] = (order_id, result)
            if working.status == OrderStatus.FILLED.value:
                self._client_ids[working.client_order_id] = result
                self._client_requests[working.client_order_id] = (
                    working.symbol,
                    working.side,
                    working.quantity,
                    working.limit_price,
                )
                self._working.pop(order_id, None)
            self._append_ledger(result, raw_price, fill_price, commission, fill_id=fill_id)
            return result

    def cancel_order(self, order_id: str) -> OrderResult:
        with self._lock:
            working = self._working.get(order_id)
            if working is None:
                raise ValueError(f"no working order {order_id}")
            if working.status in {OrderStatus.FILLED.value, OrderStatus.CANCELLED.value}:
                raise ValueError(f"order {order_id} is {working.status}")

            working.status = OrderStatus.CANCELLED.value
            result = OrderResult(
                working.order_id,
                working.client_order_id,
                working.symbol,
                working.side,
                working.quantity,
                working.average_fill_price if working.filled_quantity > 0 else Decimal("0"),
                OrderStatus.CANCELLED.value,
                filled_quantity=working.filled_quantity,
                remaining_quantity=working.remaining_quantity,
                metadata=dict(working.metadata),
            )
            self._orders[order_id] = result
            self._working.pop(order_id, None)
            if working.filled_quantity > 0:
                self._client_ids[working.client_order_id] = result
                self._client_requests[working.client_order_id] = (
                    working.symbol,
                    working.side,
                    working.quantity,
                    working.limit_price,
                )
            return result

    def get_working_orders(self) -> list[WorkingOrder]:
        with self._lock:
            return [
                WorkingOrder(
                    w.order_id,
                    w.client_order_id,
                    w.symbol,
                    w.side,
                    w.quantity,
                    w.limit_price,
                    w.filled_quantity,
                    w.average_fill_price,
                    w.status,
                    w.created_at,
                    set(w.applied_fill_ids),
                    dict(w.metadata),
                )
                for w in self._working.values()
            ]

    def get_positions(self) -> list[Position]:
        with self._lock:
            return [
                Position(p.symbol, p.quantity, p.average_price, p.opened_at)
                for p in self._positions.values()
            ]

    def get_account(self) -> AccountSnapshot:
        with self._lock:
            unrealized = Decimal("0")
            for pos in self._positions.values():
                last = self._last_prices.get(pos.symbol)
                if last is None:
                    continue
                direction = Decimal("1") if pos.quantity > 0 else Decimal("-1")
                unrealized += (last - pos.average_price) * abs(pos.quantity) * direction
            equity = self._balance + unrealized
            return AccountSnapshot(
                balance=self._balance,
                equity=equity,
                realized_pnl=self._realized_pnl,
                open_positions=len(self._positions),
                commission_paid=self._commission_paid,
            )

    def close_position(self, symbol: str, price: float | Decimal) -> OrderResult:
        price = Decimal(str(price))
        if not price.is_finite() or price <= 0:
            raise ValueError("close price must be finite and positive")
        symbol = symbol.strip().upper()
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                raise ValueError(f"no open position for {symbol}")
            side = Side.SELL if pos.quantity > 0 else Side.BUY
            qty = abs(pos.quantity)
        return self.place_order(
            OrderRequest(symbol, side, qty, price, f"close-{uuid4()}")
        )

    @property
    def commission_paid(self) -> Decimal:
        with self._lock:
            return self._commission_paid

    def ledger_entries(self) -> list[dict]:
        if self._ledger_path is None or not self._ledger_path.exists():
            return []
        entries = []
        with self._ledger_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
