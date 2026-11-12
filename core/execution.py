"""The only supported path from strategy orders to a broker adapter."""
from __future__ import annotations

from decimal import Decimal
from threading import RLock

from brokers.base import Broker
from core.models import OrderRequest, OrderResult
from core.risk import RiskEngine


class ExecutionService:
    def __init__(self, broker: Broker, risk: RiskEngine) -> None:
        self.broker = broker
        self.risk = risk
        # Serialize account snapshot -> risk decision -> broker submission. Without
        # this lock concurrent callers can all pass using the same stale position count.
        self._submission_lock = RLock()

    def submit(self, order: OrderRequest) -> OrderResult:
        """Submit only after a serialized, net-marked-PnL risk check."""
        with self._submission_lock:
            account = self.broker.get_account()
            unrealized_pnl = account.equity - account.balance
            positions = self.broker.get_positions()
            symbol = order.symbol.strip().upper()
            symbol_exposure = sum(
                (abs(position.quantity) * position.average_price
                 for position in positions if position.symbol.upper() == symbol),
                Decimal("0"),
            )
            decision = self.risk.evaluate(
                order,
                daily_realized_pnl=(
                    account.daily_realized_pnl if account.daily_accounting_available
                    else account.realized_pnl
                ),
                unrealized_pnl=unrealized_pnl,
                commission_paid=(
                    account.daily_commission_paid if account.daily_accounting_available
                    else account.commission_paid
                ),
                open_positions=account.open_positions,
                symbol_exposure=symbol_exposure,
                current_equity=account.equity,
                peak_equity=account.peak_equity,
            )
            if not decision.allowed:
                raise PermissionError(f"order rejected by risk engine: {decision.reason}")
            return self.broker.place_order(order)

    def close_position(self, symbol: str, price: Decimal) -> OrderResult:
        """Close an existing paper position; risk stops new entries, not risk-reducing exits."""
        with self._submission_lock:
            if not price.is_finite() or price <= 0:
                raise ValueError("close price must be a finite positive value")
            positions = {position.symbol: position for position in self.broker.get_positions()}
            if symbol not in positions:
                raise ValueError(f"no open position for {symbol}")
            return self.broker.close_position(symbol, price)
