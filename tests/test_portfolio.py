from decimal import Decimal
import unittest

from brokers.paper import PaperBroker
from core.models import OrderRequest, Side
from core.portfolio import PortfolioTracker


class PortfolioTests(unittest.TestCase):
    def test_snapshot_notional_and_symbols(self):
        broker = PaperBroker(Decimal("1000"))
        broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("2"), Decimal("10"), "a"))
        broker.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("5"), "b"))
        snap = PortfolioTracker(broker).snapshot()
        self.assertEqual(snap.account.open_positions, 2)
        self.assertEqual(snap.total_notional, Decimal("25"))
        self.assertEqual(snap.symbols, ["EURUSD", "GBPUSD"])


if __name__ == "__main__":
    unittest.main()
