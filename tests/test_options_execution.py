from datetime import datetime, timedelta, timezone
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path

from brokers.deriv.contracts import ContractBasis, DerivBuyResult, DerivOptionsIntent, DerivProposal, DurationUnit
from brokers.deriv.ledger import DerivContractLedger
from brokers.deriv.options_execution import OptionsExecutionPolicy, OptionsExecutionService


class FakeGateway:
    def __init__(self):
        self.buy_calls = 0
    def get_proposal(self, intent):
        return DerivProposal("proposal-1", Decimal("2"), Decimal("3"))
    def buy_contract(self, proposal_id, max_price, *, client_intent_id):
        self.buy_calls += 1
        return DerivBuyResult("contract-1", "txn-1", Decimal("2"), Decimal("3"), "USD")
    def get_open_contract(self, contract_id):
        raise NotImplementedError
    def get_portfolio(self):
        return []
    def sell_contract(self, contract_id, min_price="0"):
        raise NotImplementedError


def make_intent(identity="intent-1"):
    return DerivOptionsIntent(
        "R_100", "CALL", "USD", Decimal("2"), ContractBasis.STAKE,
        5, DurationUnit.TICKS, identity,
    )


class OptionsExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = DerivContractLedger(Path(self.tmp.name) / "ledger.sqlite")
        self.gateway = FakeGateway()
        self.now = datetime.now(timezone.utc)
        self.policy = OptionsExecutionPolicy(
            kill_switch_engaged=False, operator_enabled=True, account_mode="demo",
            max_stake=Decimal("5"), max_aggregate_stake=Decimal("10"),
        )
        self.service = OptionsExecutionService(
            self.gateway, self.ledger, self.policy, clock=lambda: datetime.now(timezone.utc),
        )
    def tearDown(self):
        self.tmp.cleanup()

    def test_default_policy_blocks_before_gateway_buy(self):
        service = OptionsExecutionService(
            self.gateway, self.ledger, OptionsExecutionPolicy(), clock=lambda: self.now,
        )
        proposal = service.request_proposal(make_intent())
        with self.assertRaises(PermissionError):
            service.buy(make_intent(), proposal, proposal)
        self.assertEqual(self.gateway.buy_calls, 0)

    def test_proposal_buy_is_durably_recorded(self):
        intent = make_intent()
        proposal = self.service.request_proposal(intent)
        result = self.service.buy(intent, proposal, proposal)
        self.assertEqual(result.contract_id, "contract-1")
        self.assertEqual([e["event_type"] for e in self.ledger.events(intent.client_intent_id)],
                         ["proposal_received", "buy_requested", "contract_bought"])
        reopened = DerivContractLedger(Path(self.tmp.name) / "ledger.sqlite")
        self.assertTrue(reopened.has_intent(intent.client_intent_id))

    def test_duplicate_buy_is_rejected(self):
        intent = make_intent()
        proposal = self.service.request_proposal(intent)
        self.service.buy(intent, proposal, proposal)
        with self.assertRaises(PermissionError):
            self.service.buy(intent, proposal, proposal)
        self.assertEqual(self.gateway.buy_calls, 1)

    def test_stale_proposal_is_rejected(self):
        intent = make_intent()
        proposal = self.service.request_proposal(intent)
        with self.assertRaises(PermissionError):
            self.service.buy(intent, proposal, proposal)
        self.assertEqual(self.gateway.buy_calls, 0)

    def test_real_account_mode_is_rejected(self):
        intent = make_intent()
        proposal = self.service.request_proposal(intent)
        self.service._policy = OptionsExecutionPolicy(
            kill_switch_engaged=False, operator_enabled=True, account_mode="real",
            max_stake=Decimal("5"), max_aggregate_stake=Decimal("10"),
        )
        with self.assertRaises(PermissionError):
            self.service.buy(intent, proposal, proposal)
        self.assertEqual(self.gateway.buy_calls, 0)

    def test_ambiguous_buy_keeps_stake_reserved(self):
        intent = make_intent()
        self.ledger.append(intent.client_intent_id, "buy_requested", {"amount": "2"})
        self.ledger.append(intent.client_intent_id, "buy_unknown", {"reason": "timeout"})
        self.assertEqual(self.ledger.open_stake_total(), "2")

    def test_buy_claim_is_atomic_and_single_use(self):
        self.ledger.claim_buy("single-use")
        with self.assertRaises(PermissionError):
            self.ledger.claim_buy("single-use")

    def test_unrecorded_proposal_cannot_be_bought(self):
        intent = make_intent()
        proposal = DerivProposal("not-recorded", Decimal("2"), Decimal("3"))
        with self.assertRaises(PermissionError):
            self.service.buy(intent, proposal)
        self.assertEqual(self.gateway.buy_calls, 0)

    def test_ambiguous_buy_is_not_retried(self):
        class AmbiguousGateway(FakeGateway):
            def buy_contract(self, *args, **kwargs):
                self.buy_calls += 1
                raise TimeoutError("connection lost")
        gateway = AmbiguousGateway()
        service = OptionsExecutionService(gateway, self.ledger, self.policy, clock=lambda: self.now)
        intent = make_intent()
        proposal = service.request_proposal(intent)
        with self.assertRaises(TimeoutError):
            service.buy(intent, proposal, proposal)
        with self.assertRaises(PermissionError):
            service.buy(intent, proposal, proposal)
        self.assertEqual(gateway.buy_calls, 1)
        self.assertEqual(self.ledger.events(intent.client_intent_id)[-1]["event_type"], "buy_unknown")


if __name__ == "__main__":
    unittest.main()
