import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from brokers.paper.persistent import CrashInjectedError
from core.models import OrderRequest, Side


class CrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        self.now = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def broker(self):
        return PersistentPaperBroker(
            Decimal("1000"),
            database_path=self.db,
            clock=lambda: self.now,
        )

    def test_crash_before_commit_rolls_back_and_recovers_prior_state(self):
        first = self.broker()
        first.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "a"))
        events_before = first.ledger_event_count()
        balance_before = first.get_account().balance

        first.inject_crash_before_commit("paper_order")
        with self.assertRaises(CrashInjectedError):
            first.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("5"), "b"))

        recovered = self.broker()
        self.assertEqual(recovered.ledger_event_count(), events_before)
        self.assertEqual(recovered.get_account().balance, balance_before)
        self.assertEqual(recovered.get_account().open_positions, 1)
        symbols = {p.symbol for p in recovered.get_positions()}
        self.assertEqual(symbols, {"EURUSD"})
        summary = recovered.reconcile()
        self.assertTrue(summary["chain_ok"])
        self.assertEqual(summary["open_positions"], 1)

    def test_working_order_survives_restart(self):
        first = self.broker()
        opened = first.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("4"), Decimal("1.2"), "w")
        )
        first.apply_partial_fill(opened.order_id, Decimal("1"))
        recovered = self.broker()
        working = recovered.get_working_orders()
        self.assertEqual(len(working), 1)
        self.assertEqual(working[0].filled_quantity, Decimal("1"))
        self.assertEqual(working[0].remaining_quantity, Decimal("3"))
        done = recovered.apply_partial_fill(opened.order_id, Decimal("3"))
        self.assertEqual(done.status, "filled")
        self.assertEqual(recovered.get_positions()[0].quantity, Decimal("4"))


if __name__ == "__main__":
    unittest.main()
