import unittest

from brokers.deriv import DerivBroker
from brokers.mt5 import MT5Broker


class DisabledBrokerTests(unittest.TestCase):
    def test_deriv_cannot_construct(self):
        with self.assertRaises(RuntimeError):
            DerivBroker()

    def test_mt5_cannot_construct(self):
        with self.assertRaises(RuntimeError):
            MT5Broker()


if __name__ == "__main__":
    unittest.main()
