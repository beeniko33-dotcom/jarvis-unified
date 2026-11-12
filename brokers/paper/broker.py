"""Deterministic in-memory paper broker with optional audit ledger; no network or real-money execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import uuid4

from core.models import AccountSnapshot, OrderRequest, OrderResult, Position, Side


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperBroker:
    """Paper execution adapter.

    Features for Level 2:
    - Mark-to-market equity via last known prices
    - Configurable commission (per-side) and slippage (bps)
    - Optional JSONL audit ledger for filled orders
    - Thread-safe via RLock
    - Idempotent client_order_id handling (compares original request)
    """

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
        # original request fingerprint for idempotency: (symbol, side, qty, raw_price)
        self._client_requests: dict[str, tuple[str, Side, Decimal, Decimal]] = {}
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
        self, result: OrderResult, raw_price: Decimal, fill_price: Decimal, commission: Decimal
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
            "raw_price": str(raw_price),
            "fill_price": str(fill_price),
            "commission": str(commission),
            "status": result.status,
            "balance": str(self._balance),
            "equity": str(self.get_account().equity),
            "realized_pnl": str(self._realized_pnl),
            "commission_paid": str(self._commission_paid),
            "open_positions": len(self._positions),
        }
        with self._ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def set_last_price(self, symbol: str, price: Decimal | float | str) -> None:
        """Update last known price for mark-to-market equity."""
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

            raw_price = order.price
            fill_price = self._apply_slippage(order.side, raw_price)
            commission = self._commission_per_side

            current = self._positions.get(symbol)
            signed = order.quantity if order.side == Side.BUY else -order.quantity

            if current and current.quantity * signed < 0:
                # Closing or reducing
                closing = min(abs(current.quantity), order.quantity)
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

                excess = order.quantity - closing
                if excess > 0:
                    # Flip residual into new position
                    new_signed = (Decimal("1") if signed > 0 else Decimal("-1")) * excess
                    self._positions[symbol] = Position(symbol, new_signed, fill_price)
            elif current:
                # Adding to existing position
                total = abs(current.quantity) + order.quantity
                avg = (
                    abs(current.quantity) * current.average_price + order.quantity * fill_price
                ) / total
                self._positions[symbol] = Position(
                    symbol, current.quantity + signed, avg, current.opened_at
                )
                self._balance -= commission
                self._commission_paid += commission
            else:
                # New position
                self._positions[symbol] = Position(symbol, signed, fill_price)
                self._balance -= commission
                self._commission_paid += commission

            self._last_prices[symbol] = fill_price

            result = OrderResult(
                str(uuid4()),
                order.client_order_id,
                symbol,
                order.side,
                order.quantity,
                fill_price,
                "filled",
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
        """Return ledger records if a ledger path is configured."""
        if self._ledger_path is None or not self._ledger_path.exists():
            return []
        entries = []
        with self._ledger_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
