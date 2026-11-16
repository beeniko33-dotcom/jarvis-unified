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
    )
    values.update(overrides)
    return ExperimentEvidence(**values)


class InnovationLabTests(unittest.TestCase):
    def test_strong_candidate_remains_research_only_without_verifier(self):
        result = assess_experiment(evidence())
        self.assertEqual(result.disposition, ExperimentDisposition.RESEARCH_ONLY)
        self.assertIn("provider-authenticity verifier is unavailable", result.reasons[0])

    def test_caller_cannot_supply_provenance_verified_boolean(self):
        with self.assertRaises(TypeError):
            evidence(data_provenance_verified=True)

    def test_missing_costs_is_research_only(self):
        result = assess_experiment(evidence(transaction_costs_included=False))
        self.assertEqual(result.disposition, ExperimentDisposition.RESEARCH_ONLY)
        self.assertIn("transaction costs are not included", result.reasons)

    def test_in_sample_data_is_research_only(self):
        result = assess_experiment(evidence(out_of_sample=False))
        self.assertEqual(result.disposition, ExperimentDisposition.RESEARCH_ONLY)
        self.assertIn("out-of-sample evaluation is missing", result.reasons)

    def test_metrics_are_reported_without_granting_trust(self):
        result = assess_experiment(evidence())
        self.assertEqual(result.return_improvement_pct_points, Decimal("3"))
        self.assertEqual(result.drawdown_improvement_pct_points, Decimal("2"))
        self.assertNotEqual(result.disposition, ExperimentDisposition.HUMAN_REVIEW_REQUIRED)

    def test_negative_sample_size_is_rejected(self):
        with self.assertRaises(ValueError):
            assess_experiment(evidence(sample_size=-1))

    def test_invalid_percentage_fails_closed(self):
        with self.assertRaises(ValueError):
            assess_experiment(evidence(candidate_net_return_pct=Decimal("NaN")))


if __name__ == "__main__":
    unittest.main()
