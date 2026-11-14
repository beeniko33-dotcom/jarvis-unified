import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.models import OrderRequest, Side


class PersistentPaperBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def broker(self, commission="0"):
        return PersistentPaperBroker(
            Decimal("1000"), database_path=self.db,
            commission_per_side=Decimal(commission),
            clock=lambda: self.now,
        )

    def order(self, side=Side.BUY, qty="1", price="10", cid="one"):
        return OrderRequest("EURUSD", side, Decimal(qty), Decimal(price), cid)

    def test_restart_restores_positions_balance_and_idempotency(self):
        first = self.broker()
        fill = first.place_order(self.order())
        before = first.get_account()
        first = None

        recovered = self.broker()
        after = recovered.get_account()
        self.assertEqual(after.balance, before.balance)
        self.assertEqual(after.open_positions, 1)
        self.assertEqual(recovered.get_positions()[0].quantity, Decimal("1"))
        replay = recovered.place_order(self.order())
        self.assertEqual(replay.order_id, fill.order_id)
        self.assertEqual(recovered.get_account().open_positions, 1)
        self.assertTrue(recovered.verify_ledger())

    def test_utc_daily_realized_pnl_and_commissions_roll_over(self):
        broker = self.broker(commission="0.25")
        broker.place_order(self.order())
        broker.place_order(self.order(Side.SELL, price="12", cid="close"))
        account = broker.get_account()
        self.assertTrue(account.daily_accounting_available)
        self.assertEqual(account.daily_realized_pnl, Decimal("2"))
        self.assertEqual(account.daily_commission_paid, Decimal("0.5"))

        self.now = datetime(2026, 11, 12, 0, 1, tzinfo=timezone.utc)
        next_day = broker.get_account()
        self.assertEqual(next_day.daily_realized_pnl, Decimal("0"))
        self.assertEqual(next_day.daily_commission_paid, Decimal("0"))
        self.assertEqual(next_day.realized_pnl, Decimal("2"))

    def test_multiple_instances_serialize_and_preserve_idempotency(self):
        first = self.broker()
        second = self.broker()

        def submit(index):
            broker = first if index % 2 == 0 else second
            return broker.place_order(self.order(cid=f"order-{index}")).order_id

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(submit, range(8)))
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(first.get_account().open_positions, 1)
        self.assertEqual(len(first.get_positions()), 1)
        self.assertTrue(second.verify_ledger())

    def test_peak_equity_is_persisted_and_drawdown_is_reported_after_restart(self):
        broker = self.broker()
        broker.place_order(self.order())
        broker.set_last_price("EURUSD", "5")
        first = broker.get_account()
        self.assertEqual(first.peak_equity, Decimal("1000"))
        self.assertGreater(first.drawdown_pct, Decimal("0"))
        recovered = self.broker()
        after = recovered.get_account()
        self.assertEqual(after.peak_equity, Decimal("1000"))
        self.assertEqual(after.drawdown_pct, first.drawdown_pct)
    def test_tampered_event_is_detected_and_broker_fails_closed(self):
        broker = self.broker()
        broker.place_order(self.order())
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE paper_events SET payload='{}' WHERE seq=2")
            db.commit()
        with self.assertRaises(RuntimeError):
            broker.get_account()
        with self.assertRaises(RuntimeError):
            self.broker()

    def test_tampered_snapshot_is_detected(self):
        broker = self.broker()
        broker.place_order(self.order())
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE paper_state SET payload='{}' WHERE singleton=1")
            db.commit()
        with self.assertRaises(RuntimeError):
            broker.get_account()


if __name__ == "__main__":
    unittest.main()
