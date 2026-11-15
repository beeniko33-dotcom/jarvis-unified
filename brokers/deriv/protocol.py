"""Capability contract for Deriv Options; separate from spot Broker."""
from __future__ import annotations

from typing import Protocol

from brokers.deriv.contracts import (
    DerivBuyResult,
    DerivOpenContract,
    DerivOptionsIntent,
    DerivPortfolioContract,
    DerivProposal,
    DerivSellResult,
)


class DerivOptionsGateway(Protocol):
    """Transport-level capability. Production adapter must still be wrapped by ExecutionService."""

    def get_proposal(self, intent: DerivOptionsIntent) -> DerivProposal: ...
    def buy_contract(self, proposal_id: str, max_price: str, *, client_intent_id: str) -> DerivBuyResult: ...
    def get_open_contract(self, contract_id: str) -> DerivOpenContract: ...
    def get_portfolio(self) -> list[DerivPortfolioContract]: ...
    def sell_contract(self, contract_id: str, min_price: str = "0") -> DerivSellResult: ...
