"""Fail-closed orchestration for Deriv Options; no transport is created here."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from brokers.deriv.contracts import DerivBuyResult, DerivOptionsIntent, DerivProposal
from brokers.deriv.ledger import DerivContractLedger
from brokers.deriv.protocol import DerivOptionsGateway


@dataclass(frozen=True)
class OptionsExecutionPolicy:
    """Explicit policy snapshot. Defaults are intentionally non-operational."""
    kill_switch_engaged: bool = True
    operator_enabled: bool = False
    account_mode: str = "demo"
    max_stake: Decimal = Decimal("0")
    max_aggregate_stake: Decimal = Decimal("0")
    proposal_max_age_seconds: int = 30


class OptionsExecutionService:
    """The sole orchestration path for proposal/buy; gateway is injected explicitly."""

    def __init__(
        self,
        gateway: DerivOptionsGateway,
        ledger: DerivContractLedger,
        policy: OptionsExecutionPolicy,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._gateway = gateway
        self._ledger = ledger
        self._policy = policy
        self._clock = clock

    def request_proposal(self, intent: DerivOptionsIntent) -> DerivProposal:
        if self._ledger.has_intent(intent.client_intent_id):
            raise PermissionError("intent identity already exists; use a new identity")
        proposal = self._gateway.get_proposal(intent)
        self._ledger.append(intent.client_intent_id, "proposal_received", {
            "proposal_id": proposal.proposal_id,
            "underlying_symbol": intent.underlying_symbol,
            "contract_type": intent.contract_type,
            "currency": intent.currency,
            "amount": str(intent.amount),
            "basis": intent.basis.value,
            "duration": intent.duration,
            "duration_unit": intent.duration_unit.value,
            "ask_price": str(proposal.ask_price),
            "payout": str(proposal.payout),
        })
        return proposal

    def buy(self, intent: DerivOptionsIntent, proposal: DerivProposal) -> DerivBuyResult:
        policy = self._policy
        if policy.account_mode != "demo":
            raise PermissionError("only an explicitly identified demo account is allowed")
        if policy.kill_switch_engaged:
            raise PermissionError("options execution kill switch is engaged")
        if not policy.operator_enabled:
            raise PermissionError("explicit operator enablement is required")
        if policy.max_stake <= 0 or intent.amount > policy.max_stake:
            raise PermissionError("stake exceeds configured positive maximum")
        if policy.max_aggregate_stake <= 0:
            raise PermissionError("aggregate exposure limit must be configured")
        events = self._ledger.events(intent.client_intent_id)
        proposal_events = [
            event for event in events
            if event["event_type"] == "proposal_received"
            and event["payload"].get("proposal_id") == proposal.proposal_id
        ]
        if not proposal_events:
            raise PermissionError("proposal was not issued and recorded for this intent")
        if any(e["event_type"] in {"buy_requested", "buy_unknown", "contract_bought"} for e in events):
            raise PermissionError("buy already attempted; reconcile before any retry")
        if len(proposal_events) != 1:
            raise PermissionError("proposal identity is ambiguous; reconcile before proceeding")
        now = self._clock()
        proposal_received_at = datetime.fromisoformat(proposal_events[0]["occurred_at"])
        if proposal_received_at.tzinfo is None or now.tzinfo is None:
            raise ValueError("proposal timestamps must be timezone-aware")
        age = (now - proposal_received_at).total_seconds()
        if age < 0 or age > policy.proposal_max_age_seconds:
            raise PermissionError("proposal is stale or timestamp is invalid")
        if proposal.ask_price > intent.amount and intent.basis.value == "stake":
            raise PermissionError("proposal ask price exceeds requested stake")
        projected = Decimal(self._ledger.open_stake_total()) + intent.amount
        if projected > policy.max_aggregate_stake:
            raise PermissionError("aggregate stake limit would be exceeded")

        # Durable intent is recorded before the non-idempotent remote side effect.
        self._ledger.append(intent.client_intent_id, "buy_requested", {
            "proposal_id": proposal.proposal_id,
            "amount": str(intent.amount),
            "currency": intent.currency,
            "ask_price": str(proposal.ask_price),
            "payout": str(proposal.payout),
        })
        try:
            result = self._gateway.buy_contract(
                proposal.proposal_id, str(proposal.ask_price),
                client_intent_id=intent.client_intent_id,
            )
        except Exception:
            # Ambiguous network outcome is terminal until remote reconciliation.
            self._ledger.append(intent.client_intent_id, "buy_unknown", {
                "proposal_id": proposal.proposal_id,
                "reason": "transport outcome ambiguous; reconciliation required",
            })
            raise
        self._ledger.append(intent.client_intent_id, "contract_bought", {
            "contract_id": result.contract_id,
            "transaction_id": result.transaction_id,
            "buy_price": str(result.buy_price),
            "payout": str(result.payout),
            "currency": result.currency,
        }, contract_id=result.contract_id)
        return result
