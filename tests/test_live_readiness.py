"""Tests for the mandatory demo-evidence gate."""
import unittest
from decimal import Decimal

from research.live_readiness import (
    DemoEvidenceSummary,
    LiveReadinessStatus,
    assess_live_readiness,
)


def evidence(**overrides):
    values = dict(
        consecutive_utc_days=30,
        realized_trade_events=120,
        expectancy_after_costs=Decimal("0.15"),
        profit_factor=Decimal("1.35"),
        max_drawdown_pct=Decimal("6"),
        rejected_entry_rate=Decimal("0.05"),
        slippage_coverage_pct=Decimal("100"),
        open_positions_at_end=0,
        ledger_integrity_verified=True,
    )
    values.update(overrides)
    return DemoEvidenceSummary(**values)


class LiveReadinessTests(unittest.TestCase):
    def test_threshold_passes_only_to_manual_review_not_live(self):
        result = assess_live_readiness(evidence())
        self.assertEqual(result.status, LiveReadinessStatus.ELIGIBLE_FOR_MANUAL_REVIEW)
        self.assertFalse(result.live_trading_enabled)
        self.assertIn("independent provider authenticity", " ".join(result.reasons))
        self.assertIn("live execution remains unavailable", " ".join(result.reasons))

    def test_less_than_30_consecutive_days_is_blocked(self):
        result = assess_live_readiness(evidence(consecutive_utc_days=29))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)
        self.assertIn("requires 30 consecutive UTC demo days", result.reasons)

    def test_day_count_does_not_substitute_for_trade_sample(self):
        result = assess_live_readiness(evidence(realized_trade_events=99))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_missing_risk_metrics_block(self):
        result = assess_live_readiness(evidence(rejected_entry_rate=None))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_negative_expectancy_blocks(self):
        result = assess_live_readiness(evidence(expectancy_after_costs=Decimal("-0.01")))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_excessive_drawdown_blocks(self):
        result = assess_live_readiness(evidence(max_drawdown_pct=Decimal("10.01")))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_unverified_ledger_blocks(self):
        result = assess_live_readiness(evidence(ledger_integrity_verified=False))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_open_positions_block(self):
        result = assess_live_readiness(evidence(open_positions_at_end=1))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)

    def test_missing_slippage_coverage_blocks(self):
        result = assess_live_readiness(evidence(slippage_coverage_pct=None))
        self.assertEqual(result.status, LiveReadinessStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
