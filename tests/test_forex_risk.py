from decimal import Decimal
import unittest

from research.forex_risk import ForexRiskRequest, assess_position_size


class ForexRiskTests(unittest.TestCase):
    def request(self, **changes):
        values = dict(
            account_equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            stop_distance_pips=Decimal("20"),
            pip_value_per_unit=Decimal("0.0001"),
            daily_loss_used=Decimal("0.005"),
            daily_loss_limit=Decimal("0.03"),
            max_risk_fraction=Decimal("0.01"),
            max_units=Decimal("1000000"),
        )
        values.update(changes)
        return ForexRiskRequest(**values)

    def test_sizes_position_within_one_percent_risk_cap(self):
        result = assess_position_size(self.request())
        self.assertTrue(result.approved_for_research)
        self.assertLessEqual(result.projected_loss, result.risk_budget)
        self.assertEqual(result.reason, "sizing estimate only; no order is authorized")

    def test_rejects_risk_above_configured_cap(self):
        result = assess_position_size(self.request(risk_fraction=Decimal("0.02")))
        self.assertFalse(result.approved_for_research)
        self.assertIn("exceeds", result.reason)

    def test_rejects_when_daily_loss_limit_is_reached(self):
        result = assess_position_size(self.request(daily_loss_used=Decimal("0.03")))
        self.assertFalse(result.approved_for_research)
        self.assertIn("daily loss", result.reason)

    def test_caps_units(self):
        result = assess_position_size(self.request(max_units=Decimal("100")))
        self.assertTrue(result.approved_for_research)
        self.assertEqual(result.units, Decimal("100"))

    def test_rejects_float_and_invalid_inputs(self):
        with self.assertRaises(ValueError):
            assess_position_size(self.request(account_equity=10000))
        with self.assertRaises(ValueError):
            assess_position_size(self.request(stop_distance_pips=Decimal("0")))
        with self.assertRaises(ValueError):
            assess_position_size(self.request(daily_loss_used=Decimal("-0.1")))


if __name__ == "__main__":
    unittest.main()
