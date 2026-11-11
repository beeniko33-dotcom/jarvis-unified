"""MT5 adapter skeleton — intentionally disabled."""
from __future__ import annotations

from decimal import Decimal

from core.models import AccountSnapshot, OrderRequest, OrderResult, Position


class MT5Broker:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "MT5 adapter is disabled. Paper mode only. "
            "Enable only after measured paper results and explicit operator unlock."
        )

    def place_order(self, order: OrderRequest) -> OrderResult:  # pragma: no cover
        raise RuntimeError("MT5 adapter is disabled")

    def get_positions(self) -> list[Position]:  # pragma: no cover
        raise RuntimeError("MT5 adapter is disabled")

    def get_account(self) -> AccountSnapshot:  # pragma: no cover
        raise RuntimeError("MT5 adapter is disabled")

    def close_position(self, symbol: str, price: Decimal) -> OrderResult:  # pragma: no cover
        raise RuntimeError("MT5 adapter is disabled")
