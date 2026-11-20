import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from research.forex_forecast import Candle, Direction, forecast_direction


class ForexForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)

    def candles(self, values):
        return [
            Candle.from_values(self.now - timedelta(minutes=19-i), v, v+1, v-1, v)
            for i, v in enumerate(values)
        ]

    def test_uptrend_is_bullish_and_has_no_trade_fields(self):
        result = forecast_direction(
            self.candles([Decimal(100+i) for i in range(20)]),
            instrument="EURUSD", timeframe="M5", now=self.now,
        )
        self.assertEqual(result.direction, Direction.BULLISH)
        self.assertEqual(result.strength_score, 65)
        payload = result.to_dict()
        for forbidden in ("quantity", "entry", "stop_loss", "take_profit", "order"):
            self.assertNotIn(forbidden, payload)

    def test_downtrend_is_bearish(self):
        result = forecast_direction(
            self.candles([Decimal(120-i) for i in range(20)]),
            instrument="GBPUSD", timeframe="M15", now=self.now,
        )
        self.assertEqual(result.direction, Direction.BEARISH)

    def test_stale_data_rejected(self):
        candles = self.candles([Decimal(100+i) for i in range(20)])
        with self.assertRaisesRegex(ValueError, "stale"):
            forecast_direction(candles, instrument="EURUSD", timeframe="M5",
                               now=self.now + timedelta(hours=1))

    def test_future_data_rejected(self):
        candles = self.candles([Decimal(100+i) for i in range(20)])
        with self.assertRaisesRegex(ValueError, "future"):
            forecast_direction(candles, instrument="EURUSD", timeframe="M5",
                               now=self.now - timedelta(hours=1))

    def test_insufficient_and_out_of_order_data_rejected(self):
        candles = self.candles([Decimal(100+i) for i in range(19)])
        with self.assertRaises(ValueError):
            forecast_direction(candles, instrument="EURUSD", timeframe="M5", now=self.now)
        candles = self.candles([Decimal(100+i) for i in range(20)])
        candles[4], candles[5] = candles[5], candles[4]
        with self.assertRaisesRegex(ValueError, "chronological"):
            forecast_direction(candles, instrument="EURUSD", timeframe="M5", now=self.now)

    def test_invalid_ohlc_rejected(self):
        with self.assertRaises(ValueError):
            Candle.from_values(self.now, "100", "99", "98", "101")


if __name__ == "__main__":
    unittest.main()
