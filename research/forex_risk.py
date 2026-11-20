"""Pure Forex position-sizing and pre-trade risk checks.

Calculations only: this module does not generate trade signals, access a broker,
create orders, or change the existing paper/live execution controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True, slots=True)
class ForexRiskRequest:
    account_equity: Decimal
    risk_fraction: Decimal
    stop_distance_pips: Decimal
    pip_value_per_unit: Decimal
    daily_loss_used: Decimal = Decimal("0")
    daily_loss_limit: Decimal = Decimal("0.03")
    max_risk_fraction: Decimal = Decimal("0.01")
    max_units: Decimal = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class ForexRiskResult:
    approved_for_research: bool
    risk_budget: Decimal
    units: Decimal
    projected_loss: Decimal
    reason: str


def _positive(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")
    return value


def assess_position_size(request: ForexRiskRequest) -> ForexRiskResult:
    """Return a capped sizing estimate; approval is not execution authorization."""
    equity = _positive(request.account_equity, "account_equity")
    stop = _positive(request.stop_distance_pips, "stop_distance_pips")
    pip_value = _positive(request.pip_value_per_unit, "pip_value_per_unit")
    risk_fraction = _positive(request.risk_fraction, "risk_fraction")
    daily_limit = _positive(request.daily_loss_limit, "daily_loss_limit")
    max_risk = _positive(request.max_risk_fraction, "max_risk_fraction")
    max_units = _positive(request.max_units, "max_units")

    if not isinstance(request.daily_loss_used, Decimal) or not request.daily_loss_used.is_finite():
        raise ValueError("daily_loss_used must be a finite Decimal")
    if request.daily_loss_used < 0:
        raise ValueError("daily_loss_used cannot be negative")
    if risk_fraction > max_risk:
        return ForexRiskResult(False, Decimal("0"), Decimal("0"), Decimal("0"),
                               "requested risk exceeds configured per-trade cap")
    if request.daily_loss_used >= daily_limit:
        return ForexRiskResult(False, Decimal("0"), Decimal("0"), Decimal("0"),
                               "daily loss limit reached")

    budget = equity * risk_fraction
    remaining_daily_budget = equity * (daily_limit - request.daily_loss_used)
    budget = min(budget, remaining_daily_budget)
    raw_units = budget / (stop * pip_value)
    units = min(raw_units, max_units).quantize(Decimal("1"), rounding=ROUND_DOWN)
    if units <= 0:
        return ForexRiskResult(False, budget, Decimal("0"), Decimal("0"),
                               "risk budget is too small for one unit")
    projected_loss = units * stop * pip_value
    if projected_loss > budget:
        return ForexRiskResult(False, budget, units, projected_loss,
                               "rounded position exceeds risk budget")
    return ForexRiskResult(True, budget, units, projected_loss,
                           "sizing estimate only; no order is authorized")
