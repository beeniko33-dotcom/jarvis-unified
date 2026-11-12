from decimal import Decimal
import unittest

from brokers.paper import PaperBroker
from core.models import OrderRequest, OrderStatus, Side


class PartialFillTests(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(Decimal("1000"), commission_per_side=Decimal("0"))

    def test_working_order_partial_then_complete(self):
        opened = self.broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("10"), Decimal("1.10"), "w1")
        )
        self.assertEqual(opened.status, OrderStatus.OPEN.value)
        self.assertEqual(opened.filled_quantity, Decimal("0"))
        self.assertEqual(opened.remaining_quantity, Decimal("10"))

        partial = self.broker.apply_partial_fill(opened.order_id, Decimal("4"))
        self.assertEqual(partial.status, OrderStatus.PARTIAL.value)
        self.assertEqual(partial.filled_quantity, Decimal("4"))
        self.assertEqual(partial.remaining_quantity, Decimal("6"))
        self.assertEqual(self.broker.get_account().open_positions, 1)
        self.assertEqual(self.broker.get_positions()[0].quantity, Decimal("4"))

        done = self.broker.apply_partial_fill(opened.order_id, Decimal("6"))
        self.assertEqual(done.status, OrderStatus.FILLED.value)
        self.assertEqual(done.remaining_quantity, Decimal("0"))
        self.assertEqual(self.broker.get_positions()[0].quantity, Decimal("10"))
        self.assertEqual(len(self.broker.get_working_orders()), 0)

    def test_cancel_after_partial_keeps_filled_position(self):
        opened = self.broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("2"), "w2")
        )
        self.broker.apply_partial_fill(opened.order_id, Decimal("2"))
        cancelled = self.broker.cancel_order(opened.order_id)
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED.value)
        self.assertEqual(cancelled.filled_quantity, Decimal("2"))
        self.assertEqual(cancelled.remaining_quantity, Decimal("3"))
        self.assertEqual(self.broker.get_positions()[0].quantity, Decimal("2"))

    def test_overfill_rejected(self):
        opened = self.broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("3"), Decimal("1"), "w3")
        )
        with self.assertRaises(ValueError):
            self.broker.apply_partial_fill(opened.order_id, Decimal("4"))


if __name__ == "__main__":
    unittest.main()
