import unittest
from decimal import Decimal

from brokers.deriv.contracts import (
    ContractBasis, DerivBuyResult, DerivOpenContract, DerivOptionsIntent,
    DerivProposal, DerivSellResult, DurationUnit,
)
from brokers.deriv.endpoints import validate_demo_websocket_url


class DerivOptionsModelTests(unittest.TestCase):
    def make_intent(self, **overrides):
        values = dict(
            underlying_symbol="R_100", contract_type="CALL", currency="USD",
            amount=Decimal("1.00"), basis=ContractBasis.STAKE, duration=5,
            duration_unit=DurationUnit.TICKS, client_intent_id="intent-001",
        )
        values.update(overrides)
        return DerivOptionsIntent(**values)

    def test_valid_intent_preserves_options_semantics(self):
        intent = self.make_intent()
        self.assertEqual(intent.amount, Decimal("1.00"))
        self.assertEqual(intent.basis, ContractBasis.STAKE)
        self.assertEqual(intent.duration_unit, DurationUnit.TICKS)

    def test_rejects_non_decimal_or_non_positive_stake(self):
        for value in (1, Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.make_intent(amount=value)

    def test_rejects_invalid_duration_and_missing_identity(self):
        for duration in (0, -1, True, 1.5):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.make_intent(duration=duration)
        with self.assertRaises(ValueError):
            self.make_intent(client_intent_id=" ")

    def test_rejects_untyped_basis_and_duration_unit(self):
        with self.assertRaises(ValueError):
            self.make_intent(basis="stake")
        with self.assertRaises(ValueError):
            self.make_intent(duration_unit="t")

    def test_contract_response_models_validate_values(self):
        proposal = DerivProposal("proposal-1", Decimal("1"), Decimal("1.8"))
        bought = DerivBuyResult("contract-1", "txn-1", Decimal("1"), Decimal("1.8"), "USD")
        opened = DerivOpenContract(
            "contract-1", "open", Decimal("1"), Decimal("1.8"),
            Decimal("-0.2"), False, False, "USD",
        )
        sold = DerivSellResult("contract-1", "txn-2", Decimal("0.75"))
        self.assertEqual(proposal.proposal_id, "proposal-1")
        self.assertEqual(bought.contract_id, opened.contract_id)
        self.assertEqual(sold.sold_for, Decimal("0.75"))
        with self.assertRaises(ValueError):
            DerivSellResult("contract-1", "txn-2", Decimal("-0.01"))

    def test_demo_endpoint_only(self):
        url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=opaque"
        self.assertEqual(validate_demo_websocket_url(url), url)

    def test_real_public_wrong_host_and_wrong_path_are_rejected(self):
        urls = (
            "wss://api.derivws.com/trading/v1/options/ws/real?otp=opaque",
            "wss://api.derivws.com/trading/v1/options/ws/public",
            "wss://example.com/trading/v1/options/ws/demo?otp=opaque",
            "https://api.derivws.com/trading/v1/options/ws/demo?otp=opaque",
            "wss://api.derivws.com/trading/v1/options/ws/demo",
            "wss://user:pass@api.derivws.com/trading/v1/options/ws/demo?otp=opaque",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_demo_websocket_url(url)


if __name__ == "__main__":
    unittest.main()
