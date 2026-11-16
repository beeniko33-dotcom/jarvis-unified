"""Mandatory demo-evidence policy for future live-trading requests.

This is an eligibility assessor only. It cannot enable a broker, change runtime
mode, release a kill switch, or authorize an order. Its inputs must come from a
trusted, integrity-checked demo ledger/report; user-entered summaries are not
evidence. Provider authenticity and demo-account identity require a separate
independent integration attestation, which this prototype does not yet provide.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class LiveReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    ELIGIBLE_FOR_MANUAL_REVIEW = "eligible_for_manual_review"


@dataclass(frozen=True)
class DemoEvidenceSummary:
    consecutive_utc_days: int
    realized_trade_events: int
    expectancy_after_costs: Decimal | None
    profit_factor: Decimal | None
    max_drawdown_pct: Decimal | None
    rejected_entry_rate: Decimal | None
    slippage_coverage_pct: Decimal | None
    open_positions_at_end: int


@dataclass(frozen=True)
class LiveReadinessAssessment:
    status: LiveReadinessStatus
    reasons: tuple[str, ...]
    live_trading_enabled: bool = False
    quantitative_thresholds_met: bool = False


def assess_live_readiness(
    evidence: DemoEvidenceSummary,
    *,
    required_days: int = 30,
    minimum_realized_events: int = 100,
    minimum_profit_factor: Decimal = Decimal("1.2"),
    maximum_drawdown_pct: Decimal = Decimal("10"),
    minimum_slippage_coverage_pct: Decimal = Decimal("100"),
) -> LiveReadinessAssessment:
    """Evaluate demo evidence; success means review eligibility, never live access."""
    if required_days < 1 or minimum_realized_events < 1:
        raise ValueError("minimum evidence thresholds must be positive")
    for name, value in (
        ("minimum_profit_factor", minimum_profit_factor),
        ("maximum_drawdown_pct", maximum_drawdown_pct),
        ("minimum_slippage_coverage_pct", minimum_slippage_coverage_pct),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be a finite non-negative Decimal")

    reasons: list[str] = []
    if evidence.consecutive_utc_days < required_days:
        reasons.append(f"requires {required_days} consecutive UTC demo days")
    if evidence.realized_trade_events < minimum_realized_events:
        reasons.append(f"requires at least {minimum_realized_events} realized trade events")
    if evidence.expectancy_after_costs is None:
        reasons.append("net expectancy after fees and slippage is unavailable")
    elif not evidence.expectancy_after_costs.is_finite() or evidence.expectancy_after_costs <= 0:
        reasons.append("net expectancy after costs must be finite and positive")
    if evidence.profit_factor is None:
        reasons.append("profit factor is unavailable")
    elif not evidence.profit_factor.is_finite() or evidence.profit_factor < minimum_profit_factor:
        reasons.append(f"profit factor must be at least {minimum_profit_factor}")
    if evidence.max_drawdown_pct is None:
        reasons.append("maximum drawdown is unavailable")
    elif (
        not evidence.max_drawdown_pct.is_finite()
        or evidence.max_drawdown_pct < 0
        or evidence.max_drawdown_pct > maximum_drawdown_pct
    ):
        reasons.append(f"maximum drawdown must be between 0 and {maximum_drawdown_pct}%")
    if evidence.rejected_entry_rate is None:
        reasons.append("risk-rejected entry rate is unavailable")
    elif (
        not evidence.rejected_entry_rate.is_finite()
        or evidence.rejected_entry_rate < 0
        or evidence.rejected_entry_rate > 1
    ):
        reasons.append("risk-rejected entry rate is invalid")
    if evidence.slippage_coverage_pct is None:
        reasons.append("slippage coverage is unavailable")
    elif (
        not evidence.slippage_coverage_pct.is_finite()
        or evidence.slippage_coverage_pct < minimum_slippage_coverage_pct
        or evidence.slippage_coverage_pct > 100
    ):
        reasons.append(f"slippage coverage must be at least {minimum_slippage_coverage_pct}%")
    if evidence.open_positions_at_end != 0:
        reasons.append("all demo positions must be closed and reconciled")
    # Even when every metric passes, this prototype has no trusted demo-ledger
    # ingestion, provider/account attestation or live adapter. Keep the gate shut.
    quantitative_failures = list(reasons)
    reasons.extend((
        "trusted demo-ledger integrity and account identity integration is not implemented",
        "independent provider authenticity attestation is not implemented",
        "separate security/risk review and explicit owner approval are required",
    ))
    return LiveReadinessAssessment(
        LiveReadinessStatus.BLOCKED,
        tuple(reasons),
        live_trading_enabled=False,
        quantitative_thresholds_met=not quantitative_failures,
    )
