"""Deriv demo/live adapter skeleton.

Not wired into main runtime. Raising on construction keeps accidental use impossible
until paper validation and explicit operator unlock are complete.
"""
from __future__ import annotations

from decimal import Decimal

from core.models import AccountSnapshot, OrderRequest, OrderResult, Position


class DerivBroker:
    """Disabled adapter. Implement behind ExecutionService only after Level 3 paper validation."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "Deriv adapter is disabled. Paper mode only. "
            "Enable only after measured paper results and explicit operator unlock."
        )

    def place_order(self, order: OrderRequest) -> OrderResult:  # pragma: no cover
        raise RuntimeError("Deriv adapter is disabled")

    def get_positions(self) -> list[Position]:  # pragma: no cover
        raise RuntimeError("Deriv adapter is disabled")

    def get_account(self) -> AccountSnapshot:  # pragma: no cover
        raise RuntimeError("Deriv adapter is disabled")

    def close_position(self, symbol: str, price: Decimal) -> OrderResult:  # pragma: no cover
        raise RuntimeError("Deriv adapter is disabled")
