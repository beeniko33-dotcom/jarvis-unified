from decimal import Decimal
import unittest
from brokers.paper import PaperBroker
from core.models import OrderRequest, Side

class PaperBrokerTests(unittest.TestCase):
    def setUp(self): self.broker = PaperBroker(Decimal("1000"))
    def order(self, side=Side.BUY, qty="1", price="10", cid="a"):
        return OrderRequest("EURUSD", side, Decimal(qty), Decimal(price), cid)
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
    def test_rejects_invalid_order(self):
        with self.assertRaises(ValueError): self.broker.place_order(self.order(qty="0"))

if __name__ == "__main__": unittest.main()
