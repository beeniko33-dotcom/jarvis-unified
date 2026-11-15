from decimal import Decimal
import unittest
from concurrent.futures import ThreadPoolExecutor

from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, False))
        self.order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "test")

    def test_allows_within_limits(self):
        self.assertTrue(
            self.risk.evaluate(self.order, daily_realized_pnl=Decimal("0"), open_positions=0).allowed
        )

    def test_blocks_oversized_order(self):
        big = OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "big")
        self.assertFalse(
            self.risk.evaluate(big, daily_realized_pnl=Decimal("0"), open_positions=0).allowed
        )

    def test_daily_loss_limit(self):
        self.assertFalse(
            self.risk.evaluate(self.order, daily_realized_pnl=Decimal("-10"), open_positions=0).allowed
        )

    def test_unrealized_loss_counts_toward_limit(self):
        decision = self.risk.evaluate(
            self.order, daily_realized_pnl=Decimal("-2"),
            unrealized_pnl=Decimal("-8"), open_positions=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("loss limit", decision.reason)

    def test_commissions_count_toward_limit(self):
        decision = self.risk.evaluate(
            self.order, daily_realized_pnl=Decimal("-9.5"),
            commission_paid=Decimal("0.5"), open_positions=0,
        )
        self.assertFalse(decision.allowed)

    def test_non_decimal_order_values_are_declined_not_raised(self):
        # OrderRequest does not enforce types; the gate must decline cleanly, never raise.
        for quantity, price in (
            (0.1, Decimal("10")),
            (Decimal("0.1"), 10),
            ("0.1", Decimal("10")),
            (Decimal("0.1"), None),
            (float("nan"), Decimal("10")),
        ):
            with self.subTest(quantity=quantity, price=price):
                order = OrderRequest("EURUSD", Side.BUY, quantity, price, "typed")
                decision = self.risk.evaluate(order, daily_realized_pnl=Decimal("0"), open_positions=0)
                self.assertFalse(decision.allowed)
                self.assertIn("Decimal", decision.reason)

    def test_non_decimal_risk_inputs_are_declined_not_raised(self):
        for field_name in (
            "daily_realized_pnl",
            "unrealized_pnl",
            "commission_paid",
            "symbol_exposure",
            "reserved_symbol_notional",
            "correlated_exposure",
            "reserved_group_notional",
        ):
            for bad in (0, 1.5, "0", None):
                with self.subTest(field=field_name, value=bad):
                    kwargs = {"daily_realized_pnl": Decimal("0"), "open_positions": 0}
                    kwargs[field_name] = bad
                    decision = self.risk.evaluate(self.order, **kwargs)
                    self.assertFalse(decision.allowed)
                    self.assertIn("Decimal", decision.reason)

    def test_rejects_non_finite_pnl(self):
        decision = self.risk.evaluate(
            self.order, daily_realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("NaN"), open_positions=0,
        )
        self.assertFalse(decision.allowed)

    def test_max_open_positions(self):
        self.assertFalse(
            self.risk.evaluate(self.order, daily_realized_pnl=Decimal("0"), open_positions=2).allowed
        )

    def test_kill_switch(self):
        self.risk.engage_kill_switch()
        self.assertFalse(
            self.risk.evaluate(self.order, daily_realized_pnl=Decimal("0"), open_positions=0).allowed
        )

    def test_release_requires_operator_flag(self):
        self.risk.engage_kill_switch()
        with self.assertRaises(PermissionError):
            self.risk.release_kill_switch()

    def test_rejects_invalid_inputs(self):
        bad_qty = OrderRequest("EURUSD", Side.BUY, Decimal("-1"), Decimal("10"), "bad")
        self.assertFalse(
            self.risk.evaluate(bad_qty, daily_realized_pnl=Decimal("0"), open_positions=0).allowed
        )
        empty_symbol = OrderRequest("  ", Side.BUY, Decimal("0.1"), Decimal("10"), "empty")
        self.assertFalse(
            self.risk.evaluate(empty_symbol, daily_realized_pnl=Decimal("0"), open_positions=0).allowed
        )


    def test_required_quote_metadata_and_stale_quote_are_rejected(self):
        from datetime import datetime, timezone
        risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("10"), 2, False,
            max_quote_age_seconds=5, require_quote_metadata=True,
        ))
        now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
        missing = risk.evaluate(
            self.order, daily_realized_pnl=Decimal("0"), open_positions=0, now=now
        )
        self.assertFalse(missing.allowed)
        stale_order = OrderRequest(
            "EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "stale",
            {"quote_timestamp": "2026-11-12T11:59:00+00:00", "quote_source": "public-feed"},
        )
        stale = risk.evaluate(
            stale_order, daily_realized_pnl=Decimal("0"), open_positions=0, now=now
        )
        self.assertFalse(stale.allowed)
        self.assertIn("stale", stale.reason)

    def test_future_and_timezone_naive_quote_timestamps_are_rejected(self):
        from datetime import datetime, timezone
        risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("10"), 2, False, require_quote_metadata=True,
        ))
        now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
        for stamp in ("2026-11-12T12:01:00+00:00", "2026-11-12T11:59:59"):
            order = OrderRequest(
                "EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), stamp,
                {"quote_timestamp": stamp, "quote_source": "public-feed"},
            )
            decision = risk.evaluate(
                order, daily_realized_pnl=Decimal("0"), open_positions=0, now=now
            )
            self.assertFalse(decision.allowed)

    def test_per_symbol_exposure_cap_is_enforced(self):
        risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("10"), 2, False,
            max_symbol_exposure=Decimal("1.5"),
        ))
        decision = risk.evaluate(
            self.order, daily_realized_pnl=Decimal("0"), open_positions=0,
            symbol_exposure=Decimal("1.1"),
        )
        self.assertFalse(decision.allowed)
        self.assertIn("symbol exposure", decision.reason)

    def test_peak_equity_drawdown_limit_fails_closed_and_trips(self):
        risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("10"), 2, False,
            max_peak_drawdown_pct=Decimal("5"),
        ))
        decision = risk.evaluate(
            self.order, daily_realized_pnl=Decimal("0"), open_positions=0,
            current_equity=Decimal("950"), peak_equity=Decimal("1000"),
        )
        self.assertFalse(decision.allowed)
        self.assertIn("drawdown", decision.reason)
        missing = risk.evaluate(
            self.order, daily_realized_pnl=Decimal("0"), open_positions=0,
        )
        self.assertFalse(missing.allowed)
    def test_concurrent_evaluate_is_thread_safe(self):
        results = []

        def worker(_):
            decision = self.risk.evaluate(
                self.order, daily_realized_pnl=Decimal("0"), open_positions=0
            )
            results.append(decision.allowed)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(40)))
        self.assertTrue(all(results))
        self.assertEqual(len(results), 40)


if __name__ == "__main__":
    unittest.main()
