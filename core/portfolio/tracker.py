"""Lightweight portfolio tracker over broker account + positions."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from brokers.base import Broker
from core.models import AccountSnapshot, Position


@dataclass(frozen=True)
class PortfolioSnapshot:
    account: AccountSnapshot
    positions: list[Position]
    total_notional: Decimal
    symbols: list[str]


class PortfolioTracker:
    def __init__(self, broker: Broker) -> None:
        self.broker = broker

    def snapshot(self) -> PortfolioSnapshot:
        account = self.broker.get_account()
        positions = list(self.broker.get_positions())
        total_notional = Decimal("0")
        symbols: list[str] = []
        for pos in positions:
            total_notional += abs(pos.quantity) * pos.average_price
            symbols.append(pos.symbol)
        return PortfolioSnapshot(
            account=account,
            positions=positions,
            total_notional=total_notional,
            symbols=sorted(set(symbols)),
        )
