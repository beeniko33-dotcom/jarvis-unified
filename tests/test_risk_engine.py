from decimal import Decimal
import unittest
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits

class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, False))
        self.order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "test")
    def test_allows_within_limits(self): self.assertTrue(self.risk.evaluate(self.order, daily_realized_pnl=Decimal("0"), open_positions=0).allowed)
    def test_blocks_oversized_order(self):
        big = OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "big")
        self.assertFalse(self.risk.evaluate(big, daily_realized_pnl=Decimal("0"), open_positions=0).allowed)
    def test_daily_loss_limit(self): self.assertFalse(self.risk.evaluate(self.order, daily_realized_pnl=Decimal("-10"), open_positions=0).allowed)
    def test_kill_switch(self):
        self.risk.engage_kill_switch()
        self.assertFalse(self.risk.evaluate(self.order, daily_realized_pnl=Decimal("0"), open_positions=0).allowed)
    def test_release_requires_operator_flag(self):
        self.risk.engage_kill_switch()
        with self.assertRaises(PermissionError): self.risk.release_kill_switch()

if __name__ == "__main__": unittest.main()
