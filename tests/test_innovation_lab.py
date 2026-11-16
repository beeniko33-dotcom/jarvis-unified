"""Tests for the non-executing strategy innovation assessment gate."""
import unittest
from decimal import Decimal

from research.innovation_lab import (
    ExperimentDisposition,
    ExperimentEvidence,
    assess_experiment,
)


def evidence(**overrides):
    values = dict(
        experiment_id="exp-001",
        strategy_id="sma-v2",
        sample_size=250,
        candidate_net_return_pct=Decimal("8"),
        baseline_net_return_pct=Decimal("5"),
        candidate_max_drawdown_pct=Decimal("6"),
        baseline_max_drawdown_pct=Decimal("8"),
        transaction_costs_included=True,
        out_of_sample=True,
        data_provenance_verified=True,
    )
    values.update(overrides)
    return ExperimentEvidence(**values)


class InnovationLabTests(unittest.TestCase):
    def test_strong_candidate_only_requests_human_review(self):
        result = assess_experiment(evidence())
        self.assertEqual(result.disposition, ExperimentDisposition.HUMAN_REVIEW_REQUIRED)
        self.assertIn("human review", result.reasons[0])

    def test_unverified_data_is_research_only(self):
        result = assess_experiment(evidence(data_provenance_verified=False))
        self.assertEqual(result.disposition, ExperimentDisposition.RESEARCH_ONLY)

    def test_missing_costs_is_research_only(self):
        result = assess_experiment(evidence(transaction_costs_included=False))
        self.assertEqual(result.disposition, ExperimentDisposition.RESEARCH_ONLY)

    def test_weak_candidate_is_rejected(self):
        result = assess_experiment(evidence(candidate_net_return_pct=Decimal("4")))
        self.assertEqual(result.disposition, ExperimentDisposition.REJECTED)

    def test_excessive_drawdown_is_rejected(self):
        result = assess_experiment(evidence(candidate_max_drawdown_pct=Decimal("12")))
        self.assertEqual(result.disposition, ExperimentDisposition.REJECTED)

    def test_small_sample_is_rejected(self):
        result = assess_experiment(evidence(sample_size=20))
        self.assertEqual(result.disposition, ExperimentDisposition.REJECTED)

    def test_invalid_percentage_fails_closed(self):
        with self.assertRaises(ValueError):
            assess_experiment(evidence(candidate_net_return_pct=Decimal("NaN")))


if __name__ == "__main__":
    unittest.main()
