"""Central, fail-closed risk gate. Every order must pass this layer."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from threading import RLock
from core.models import OrderRequest

@dataclass(frozen=True)
class RiskLimits:
    max_stake_per_trade: Decimal = Decimal("5.0")
    max_daily_loss: Decimal = Decimal("10.0")
    max_open_positions: int = 2
    kill_switch: bool = True

@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str

class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        if limits.max_stake_per_trade <= 0 or limits.max_daily_loss <= 0 or limits.max_open_positions < 1:
            raise ValueError("risk limits must be positive")
        self.limits = limits
        self._halted = limits.kill_switch
        self._lock = RLock()

    @property
    def halted(self) -> bool:
        with self._lock: return self._halted

    def engage_kill_switch(self) -> None:
        with self._lock: self._halted = True

    def release_kill_switch(self, *, explicit_operator_action: bool = False) -> None:
        if not explicit_operator_action: raise PermissionError("explicit operator action required")
        with self._lock: self._halted = False

    def evaluate(self, order: OrderRequest, *, daily_realized_pnl: Decimal, open_positions: int) -> RiskDecision:
        with self._lock:
            if self._halted: return RiskDecision(False, "kill switch is engaged")
            if not order.symbol.strip(): return RiskDecision(False, "symbol is required")
            if order.quantity <= 0 or order.price <= 0: return RiskDecision(False, "quantity and price must be positive")
            notional = order.quantity * order.price
            if notional > self.limits.max_stake_per_trade: return RiskDecision(False, "per-trade notional exceeds hard limit")
            if daily_realized_pnl <= -self.limits.max_daily_loss: return RiskDecision(False, "daily loss limit reached")
            if open_positions >= self.limits.max_open_positions: return RiskDecision(False, "maximum open positions reached")
            return RiskDecision(True, "approved")
