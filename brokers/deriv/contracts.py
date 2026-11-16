"""Typed models for Deriv Options contracts.

These models deliberately do not inherit from the spot-style OrderRequest:
an options stake, proposal, contract and payout are not a quantity/price fill.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class ContractBasis(str, Enum):
    STAKE = "stake"
    PAYOUT = "payout"


class DurationUnit(str, Enum):
    TICKS = "t"
    SECONDS = "s"
    MINUTES = "m"
    HOURS = "h"
    DAYS = "d"


def _positive_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


def _required_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class DerivOptionsIntent:
    """A validated request to obtain and potentially buy one options contract."""

    underlying_symbol: str
    contract_type: str
    currency: str
    amount: Decimal
    basis: ContractBasis
    duration: int
    duration_unit: DurationUnit
    client_intent_id: str
    take_profit: Decimal | None = None
    stop_loss: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("underlying_symbol", "contract_type", "currency", "client_intent_id"):
            _required_text(name, getattr(self, name))
        _positive_decimal("amount", self.amount)
        if isinstance(self.duration, bool) or not isinstance(self.duration, int) or self.duration <= 0:
            raise ValueError("duration must be a positive integer")
        if not isinstance(self.basis, ContractBasis):
            raise ValueError("basis must be a ContractBasis")
        if not isinstance(self.duration_unit, DurationUnit):
            raise ValueError("duration_unit must be a DurationUnit")
        if self.take_profit is not None:
            _positive_decimal("take_profit", self.take_profit)
        if self.stop_loss is not None:
            _positive_decimal("stop_loss", self.stop_loss)


@dataclass(frozen=True)
class DerivProposal:
    proposal_id: str
    ask_price: Decimal
    payout: Decimal
    spot: Decimal | None = None
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _required_text("proposal_id", self.proposal_id)
        _positive_decimal("ask_price", self.ask_price)
        _positive_decimal("payout", self.payout)
        if self.spot is not None and (not self.spot.is_finite() or self.spot <= 0):
            raise ValueError("spot must be a finite positive Decimal")


@dataclass(frozen=True)
class DerivBuyResult:
    contract_id: str
    transaction_id: str
    buy_price: Decimal
    payout: Decimal
    currency: str
    longcode: str = ""

    def __post_init__(self) -> None:
        _required_text("contract_id", self.contract_id)
        _required_text("transaction_id", self.transaction_id)
        _required_text("currency", self.currency)
        _positive_decimal("buy_price", self.buy_price)
        _positive_decimal("payout", self.payout)


@dataclass(frozen=True)
class DerivOpenContract:
    contract_id: str
    status: str
    buy_price: Decimal
    payout: Decimal
    profit: Decimal
    is_sold: bool
    is_expired: bool
    currency: str

    def __post_init__(self) -> None:
        _required_text("contract_id", self.contract_id)
        _required_text("status", self.status)
        _required_text("currency", self.currency)
        for name in ("buy_price", "payout"):
            _positive_decimal(name, getattr(self, name))
        if not isinstance(self.profit, Decimal) or not self.profit.is_finite():
            raise ValueError("profit must be a finite Decimal")


@dataclass(frozen=True)
class DerivSellResult:
    contract_id: str
    transaction_id: str
    sold_for: Decimal

    def __post_init__(self) -> None:
        _required_text("contract_id", self.contract_id)
        _required_text("transaction_id", self.transaction_id)
        if not isinstance(self.sold_for, Decimal) or not self.sold_for.is_finite() or self.sold_for < 0:
            raise ValueError("sold_for must be a finite non-negative Decimal")


@dataclass(frozen=True)
class DerivPortfolioContract:
    contract_id: str
    contract_type: str
    underlying_symbol: str
    currency: str
    buy_price: Decimal
    payout: Decimal
    profit: Decimal
    status: str
