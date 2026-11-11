"""The only supported path from strategy orders to a broker adapter."""
from __future__ import annotations
from core.models import OrderRequest, OrderResult
from core.risk import RiskEngine
from brokers.base import Broker

class ExecutionService:
    def __init__(self, broker: Broker, risk: RiskEngine) -> None:
        self.broker = broker
        self.risk = risk

    def submit(self, order: OrderRequest) -> OrderResult:
        account = self.broker.get_account()
        decision = self.risk.evaluate(order, daily_realized_pnl=account.realized_pnl, open_positions=account.open_positions)
        if not decision.allowed:
            raise PermissionError(f"order rejected by risk engine: {decision.reason}")
        return self.broker.place_order(order)
