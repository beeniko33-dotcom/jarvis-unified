from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import unittest

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits


class ExecutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(Decimal("1000"))
        self.risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, True))
        self.service = ExecutionService(self.broker, self.risk)
        self.order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "order-1")

    def test_kill_switch_blocks_broker_submission(self):
        with self.assertRaises(PermissionError):
            self.service.submit(self.order)
        self.assertEqual(self.broker.get_account().open_positions, 0)

    def test_close_position_remains_available_while_kill_switch_is_engaged(self):
        self.risk.release_kill_switch(explicit_operator_action=True)
        self.service.submit(self.order)
        self.risk.engage_kill_switch()
        result = self.service.close_position("EURUSD", Decimal("11"))
        self.assertEqual(result.status, "filled")
        self.assertEqual(self.broker.get_account().open_positions, 0)

    def test_approved_order_reaches_paper_broker(self):
        self.risk.release_kill_switch(explicit_operator_action=True)
        result = self.service.submit(self.order)
        self.assertEqual(result.status, "filled")
        self.assertEqual(self.broker.get_account().open_positions, 1)

    def test_unrealized_loss_blocks_new_entry(self):
        self.risk.release_kill_switch(explicit_operator_action=True)
        self.service.submit(self.order)
        self.broker.set_last_price("EURUSD", Decimal("0.01"))
        next_order = OrderRequest("GBPUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "order-2")
        with self.assertRaises(PermissionError):
            self.service.submit(next_order)

    def test_commissions_block_new_entry_when_loss_limit_reached(self):
        broker = PaperBroker(Decimal("1000"), commission_per_side=Decimal("1"))
        risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("0.5"), 2, False))
        service = ExecutionService(broker, risk)
        first = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "fee-1")
        service.submit(first)
        second = OrderRequest("GBPUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "fee-2")
        with self.assertRaises(PermissionError):
            service.submit(second)

    def test_concurrent_submissions_cannot_exceed_position_cap(self):
        risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, False))
        service = ExecutionService(PaperBroker(Decimal("1000")), risk)

        def submit(index):
            order = OrderRequest(
                f"SYM{index}", Side.BUY, Decimal("0.1"), Decimal("10"), f"parallel-{index}"
            )
            try:
                service.submit(order)
                return True
            except PermissionError:
                return False

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(submit, range(12)))
        self.assertEqual(sum(results), 2)
        self.assertEqual(service.broker.get_account().open_positions, 2)


if __name__ == "__main__":
    unittest.main()
