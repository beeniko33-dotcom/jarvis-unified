from decimal import Decimal
import tempfile
import unittest
from pathlib import Path

from brokers.paper import PaperBroker
from core.models import OrderRequest, Side


class PaperBrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(Decimal("1000"))

    def order(self, side=Side.BUY, qty="1", price="10", cid="a", symbol="EURUSD"):
        return OrderRequest(symbol, side, Decimal(qty), Decimal(price), cid)

    def test_fill_and_idempotency(self):
        first = self.broker.place_order(self.order())
        second = self.broker.place_order(self.order())
        self.assertEqual(first.order_id, second.order_id)
        self.assertEqual(len(self.broker.get_positions()), 1)

    def test_close_calculates_realized_pnl(self):
        self.broker.place_order(self.order())
        self.broker.place_order(self.order(Side.SELL, "1", "12", "b"))
        self.assertEqual(self.broker.get_account().realized_pnl, Decimal("2"))
        self.assertEqual(self.broker.get_account().open_positions, 0)

    def test_rejects_conflicting_client_order_id(self):
        self.broker.place_order(self.order())
        with self.assertRaises(ValueError):
            self.broker.place_order(self.order(qty="2", cid="a"))

    def test_rejects_non_finite_price(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(self.order(price="NaN"))

    def test_rejects_invalid_order(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(self.order(qty="0"))

    def test_mark_to_market_equity(self):
        self.broker.place_order(self.order(qty="2", price="10"))
        # No last price yet -> equity == balance
        acct = self.broker.get_account()
        self.assertEqual(acct.equity, acct.balance)

        self.broker.set_last_price("EURUSD", Decimal("12"))
        acct = self.broker.get_account()
        # Unrealized = (12-10)*2 = 4
        self.assertEqual(acct.equity, acct.balance + Decimal("4"))

    def test_commission_and_slippage(self):
        broker = PaperBroker(
            Decimal("1000"),
            commission_per_side=Decimal("0.5"),
            slippage_bps=Decimal("10"),  # 0.1%
        )
        result = broker.place_order(self.order(price="100", qty="1"))
        # BUY slippage: 100 * 1.001 = 100.1
        self.assertEqual(result.fill_price, Decimal("100.1"))
        self.assertEqual(broker.commission_paid, Decimal("0.5"))
        acct = broker.get_account()
        self.assertEqual(acct.balance, Decimal("999.5"))  # 1000 - 0.5 commission

    def test_audit_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trades.jsonl"
            broker = PaperBroker(Decimal("1000"), ledger_path=ledger)
            broker.place_order(self.order(cid="c1"))
            broker.place_order(self.order(Side.SELL, "1", "11", "c2"))
            entries = broker.ledger_entries()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["client_order_id"], "c1")
            self.assertEqual(entries[1]["side"], "sell")
            self.assertTrue(ledger.exists())

    def test_partial_close_and_flip(self):
        self.broker.place_order(self.order(qty="3", price="10", cid="open"))
        # Sell 2 -> leave long 1
        self.broker.place_order(self.order(Side.SELL, "2", "12", "partial"))
        positions = self.broker.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].quantity, Decimal("1"))
        self.assertEqual(self.broker.get_account().realized_pnl, Decimal("4"))  # (12-10)*2


if __name__ == "__main__":
    unittest.main()
