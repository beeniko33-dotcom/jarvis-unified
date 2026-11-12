"""Central, fail-closed risk gate. Every new order must pass this layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from core.models import OrderRequest, Side


@dataclass(frozen=True)
class RiskLimits:
    max_stake_per_trade: Decimal = Decimal("5.0")
    max_daily_loss: Decimal = Decimal("10.0")
    max_open_positions: int = 2
    kill_switch: bool = True
    max_quote_age_seconds: int = 10
    require_quote_metadata: bool = False
    max_symbol_exposure: Decimal | None = None


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        if (
            not limits.max_stake_per_trade.is_finite()
            or not limits.max_daily_loss.is_finite()
            or limits.max_stake_per_trade <= 0
            or limits.max_daily_loss <= 0
            or limits.max_open_positions < 1
            or limits.max_quote_age_seconds < 0
            or (
                limits.max_symbol_exposure is not None
                and (
                    not limits.max_symbol_exposure.is_finite()
                    or limits.max_symbol_exposure <= 0
                )
            )
        ):
            raise ValueError("risk limits must be finite and positive")
        self.limits = limits
        self._halted = limits.kill_switch
        self._lock = RLock()

    @property
    def halted(self) -> bool:
        with self._lock:
            return self._halted

    def engage_kill_switch(self) -> None:
        with self._lock:
            self._halted = True

    def release_kill_switch(self, *, explicit_operator_action: bool = False) -> None:
        if not explicit_operator_action:
            raise PermissionError("explicit operator action required")
        with self._lock:
            self._halted = False

    def evaluate(
        self,
        order: OrderRequest,
        *,
        daily_realized_pnl: Decimal,
        open_positions: int,
        unrealized_pnl: Decimal = Decimal("0"),
        commission_paid: Decimal = Decimal("0"),
        symbol_exposure: Decimal = Decimal("0"),
        now: datetime | None = None,
    ) -> RiskDecision:
        with self._lock:
            if self._halted:
                return RiskDecision(False, "kill switch is engaged")
            if not isinstance(order.symbol, str) or not order.symbol.strip():
                return RiskDecision(False, "symbol is required")
            if not isinstance(order.side, Side):
                return RiskDecision(False, "unsupported order side")
            if (
                not order.quantity.is_finite()
                or not order.price.is_finite()
                or order.quantity <= 0
                or order.price <= 0
            ):
                return RiskDecision(False, "quantity and price must be finite and positive")
            pnl_values = (daily_realized_pnl, unrealized_pnl, commission_paid, symbol_exposure)
            if any(not value.is_finite() for value in pnl_values):
                return RiskDecision(False, "risk and exposure inputs must be finite")
            if commission_paid < 0 or symbol_exposure < 0:
                return RiskDecision(False, "commission and exposure cannot be negative")
            if not isinstance(open_positions, int) or open_positions < 0:
                return RiskDecision(False, "open position count is invalid")

            metadata = order.metadata or {}
            quote_time = metadata.get("quote_timestamp")
            quote_source = metadata.get("quote_source")
            if self.limits.require_quote_metadata and (not quote_time or not quote_source):
                return RiskDecision(False, "quote timestamp and source provenance are required")
            if quote_time:
                try:
                    parsed = datetime.fromisoformat(str(quote_time).replace("Z", "+00:00"))
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        return RiskDecision(False, "quote timestamp must include a timezone")
                    current = now or datetime.now(timezone.utc)
                    if current.tzinfo is None or current.utcoffset() is None:
                        return RiskDecision(False, "risk clock must include a timezone")
                    age = (current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
                    if age < 0:
                        return RiskDecision(False, "quote timestamp is in the future")
                    if age > self.limits.max_quote_age_seconds:
                        return RiskDecision(False, "quote is stale")
                except (TypeError, ValueError, OverflowError):
                    return RiskDecision(False, "quote timestamp is invalid")

            notional = order.quantity * order.price
            if notional > self.limits.max_stake_per_trade:
                return RiskDecision(False, "per-trade notional exceeds hard limit")
            if (
                self.limits.max_symbol_exposure is not None
                and symbol_exposure + notional > self.limits.max_symbol_exposure
            ):
                return RiskDecision(False, "per-symbol exposure limit exceeded")
            net_marked_pnl = daily_realized_pnl + unrealized_pnl - commission_paid
            if net_marked_pnl <= -self.limits.max_daily_loss:
                return RiskDecision(False, "net realized/unrealized loss limit reached")
            if open_positions >= self.limits.max_open_positions:
                return RiskDecision(False, "maximum open positions reached")
            return RiskDecision(True, "approved")
