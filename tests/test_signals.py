from decimal import Decimal
import unittest

from core.models import Side
from core.signals import SignalIntent


class SignalTests(unittest.TestCase):
    def test_valid_signal(self):
        s = SignalIntent("EURUSD", Side.BUY, Decimal("1"), Decimal("1.1"), 0.7, "demo")
        self.assertEqual(s.strategy, "demo")

    def test_rejects_bad_confidence(self):
        with self.assertRaises(ValueError):
            SignalIntent("EURUSD", Side.BUY, Decimal("1"), Decimal("1.1"), 1.5, "demo")


if __name__ == "__main__":
    unittest.main()
