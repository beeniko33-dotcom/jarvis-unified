"""Deterministic, non-executing evaluation gate for strategy experiments.

The prototype has no independent provider-authenticity verifier. Consequently,
caller-supplied records can never assert trusted provenance or advance a
candidate to human-review eligibility. This module never places orders,
changes runtime strategy configuration, or grants execution permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ExperimentDisposition(str, Enum):
    RESEARCH_ONLY = "research_only"
    REJECTED = "rejected"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


@dataclass(frozen=True)
class ExperimentEvidence:
    experiment_id: str
    strategy_id: str
    sample_size: int
    candidate_net_return_pct: Decimal
    baseline_net_return_pct: Decimal
    candidate_max_drawdown_pct: Decimal
    baseline_max_drawdown_pct: Decimal
    transaction_costs_included: bool
    out_of_sample: bool


@dataclass(frozen=True)
class ExperimentAssessment:
    experiment_id: str
    disposition: ExperimentDisposition
    reasons: tuple[str, ...]
    return_improvement_pct_points: Decimal
    drawdown_improvement_pct_points: Decimal


def _valid_percentage(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if value < Decimal("-100") or value > Decimal("100"):
        raise ValueError(f"{field} is outside the supported percentage range")


def assess_experiment(
    evidence: ExperimentEvidence,
    *,
    minimum_sample_size: int = 100,
    maximum_candidate_drawdown_pct: Decimal = Decimal("10"),
) -> ExperimentAssessment:
    """Assess a candidate without accepting caller-asserted provenance.

    All imported experiment records remain research-only until an independent,
    provider-authenticity verifier is implemented and its result is represented
    by a trusted internal evidence type. Local hashes and booleans are not such
    verification. No assessment can authorize broker execution.
    """
    if not evidence.experiment_id.strip() or not evidence.strategy_id.strip():
        raise ValueError("experiment_id and strategy_id are required")
    if minimum_sample_size < 1:
        raise ValueError("minimum_sample_size must be positive")
    for name in (
        "candidate_net_return_pct",
        "baseline_net_return_pct",
        "candidate_max_drawdown_pct",
        "baseline_max_drawdown_pct",
    ):
        _valid_percentage(getattr(evidence, name), name)
    if (
        not maximum_candidate_drawdown_pct.is_finite()
        or maximum_candidate_drawdown_pct < 0
    ):
        raise ValueError("maximum_candidate_drawdown_pct must be finite and non-negative")
    if evidence.candidate_max_drawdown_pct < 0 or evidence.baseline_max_drawdown_pct < 0:
        raise ValueError("drawdown percentages must be non-negative")
    if evidence.sample_size < 0:
        raise ValueError("sample_size must be non-negative")

    return_delta = evidence.candidate_net_return_pct - evidence.baseline_net_return_pct
    drawdown_delta = evidence.baseline_max_drawdown_pct - evidence.candidate_max_drawdown_pct
    restrictions = ["independent provider-authenticity verifier is unavailable"]
    if not evidence.out_of_sample:
        restrictions.append("out-of-sample evaluation is missing")
    if not evidence.transaction_costs_included:
        restrictions.append("transaction costs are not included")

    # Do not allow caller data to claim provenance or unlock the later gate.
    return ExperimentAssessment(
        evidence.experiment_id,
        ExperimentDisposition.RESEARCH_ONLY,
        tuple(restrictions),
        return_delta,
        drawdown_delta,
    )
