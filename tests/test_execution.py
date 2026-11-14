from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import tempfile
from pathlib import Path
import unittest

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits
from research.execution_observations import ExecutionObservationJournal


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

    def test_journal_records_rejected_and_approved_execution_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = ExecutionObservationJournal(Path(tmp) / "observations.sqlite")
            service = ExecutionService(self.broker, self.risk, observation_journal=journal)
            with self.assertRaises(PermissionError):
                service.submit(self.order)
            self.assertEqual(journal.list_events()[0]["event_type"], "risk_rejected")
            self.assertEqual(self.broker.get_account().open_positions, 0)
            self.risk.release_kill_switch(explicit_operator_action=True)
            result = service.submit(self.order)
            events = journal.list_events()
            self.assertEqual([e["event_type"] for e in events],
                             ["risk_rejected", "risk_approved", "broker_order_result"])
            self.assertEqual(events[-1]["data"]["order_id"], result.order_id)
            self.assertTrue(journal.verify())

    def test_journal_prevents_duplicate_client_order_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = ExecutionObservationJournal(Path(tmp) / "observations.sqlite")
            service = ExecutionService(self.broker, self.risk, observation_journal=journal)
            self.risk.release_kill_switch(explicit_operator_action=True)
            service.submit(self.order)
            with self.assertRaisesRegex(PermissionError, "already has an execution observation"):
                service.submit(self.order)
            self.assertEqual(self.broker.get_account().open_positions, 1)

    def test_journal_preserves_missing_strategy_provenance_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = ExecutionObservationJournal(Path(tmp) / "observations.sqlite")
            service = ExecutionService(self.broker, self.risk, observation_journal=journal)
            self.risk.release_kill_switch(explicit_operator_action=True)
            service.submit(self.order)
            decision = journal.list_events()[0]
            self.assertIsNone(decision["data"]["strategy_id"])
            self.assertIsNone(decision["data"]["experiment_id"])
    def test_unrealized_loss_blocks_new_entry(self):
        self.risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("0.5"), 2, True))
        self.service = ExecutionService(self.broker, self.risk)
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

    def test_execution_supplies_existing_symbol_exposure_to_risk_gate(self):
        self.risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("10"), 3, True,
            max_symbol_exposure=Decimal("1.5"),
        ))
        self.service = ExecutionService(self.broker, self.risk)
        self.risk.release_kill_switch(explicit_operator_action=True)
        self.service.submit(self.order)
        second = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "order-2")
        with self.assertRaises(PermissionError):
            self.service.submit(second)
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
