"""Deterministic in-memory paper broker; no network or real-money execution."""
from __future__ import annotations
from decimal import Decimal
from threading import RLock
from uuid import uuid4
from core.models import AccountSnapshot, OrderRequest, OrderResult, Position, Side

class PaperBroker:
    def __init__(self, starting_balance: Decimal = Decimal("10000")) -> None:
        if starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        self._balance = Decimal(starting_balance)
        self._realized_pnl = Decimal("0")
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        self._client_ids: dict[str, OrderResult] = {}
        self._lock = RLock()

    def place_order(self, order: OrderRequest) -> OrderResult:
        if not order.symbol.strip(): raise ValueError("symbol is required")
        if not isinstance(order.side, Side): raise ValueError("unsupported order side")
        if not order.quantity.is_finite() or not order.price.is_finite() or order.quantity <= 0 or order.price <= 0:
            raise ValueError("quantity and price must be finite and positive")
        if not order.client_order_id.strip(): raise ValueError("client_order_id is required")
        with self._lock:
            if order.client_order_id in self._client_ids:
                prior = self._client_ids[order.client_order_id]
                same_request = (
                    prior.symbol == order.symbol
                    and prior.side == order.side
                    and prior.quantity == order.quantity
                    and prior.fill_price == order.price
                )
                if not same_request:
                    raise ValueError("client_order_id was already used for a different order")
                return prior
            current = self._positions.get(order.symbol)
            signed = order.quantity if order.side == Side.BUY else -order.quantity
            if current and current.quantity * signed < 0:
                closing = min(abs(current.quantity), order.quantity)
                direction = Decimal("1") if current.quantity > 0 else Decimal("-1")
                pnl = (order.price - current.average_price) * closing * direction
                self._realized_pnl += pnl
                self._balance += pnl
                remaining = current.quantity + direction * -closing
                if remaining == 0:
                    self._positions.pop(order.symbol)
                else:
                    self._positions[order.symbol] = Position(order.symbol, remaining, current.average_price, current.opened_at)
                excess = order.quantity - closing
                if excess > 0:
                    self._positions[order.symbol] = Position(order.symbol, (Decimal("1") if signed > 0 else Decimal("-1")) * excess, order.price)
            elif current:
                total = abs(current.quantity) + order.quantity
                avg = (abs(current.quantity) * current.average_price + order.quantity * order.price) / total
                self._positions[order.symbol] = Position(order.symbol, current.quantity + signed, avg, current.opened_at)
            else:
                self._positions[order.symbol] = Position(order.symbol, signed, order.price)
            result = OrderResult(str(uuid4()), order.client_order_id, order.symbol, order.side, order.quantity, order.price, "filled")
            self._orders[result.order_id] = result
            self._client_ids[order.client_order_id] = result
            return result

    def get_positions(self) -> list[Position]:
        with self._lock: return [Position(p.symbol, p.quantity, p.average_price, p.opened_at) for p in self._positions.values()]

    def get_account(self) -> AccountSnapshot:
        with self._lock:
            return AccountSnapshot(self._balance, self._balance, self._realized_pnl, len(self._positions))

    def close_position(self, symbol: str, price: float | Decimal) -> OrderResult:
        price = Decimal(str(price))
        if not price.is_finite() or price <= 0:
            raise ValueError("close price must be finite and positive")
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos: raise ValueError(f"no open position for {symbol}")
            side = Side.SELL if pos.quantity > 0 else Side.BUY
            qty = abs(pos.quantity)
        return self.place_order(OrderRequest(symbol, side, qty, Decimal(str(price)), f"close-{uuid4()}"))
