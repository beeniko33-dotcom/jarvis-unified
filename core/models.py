"""Shared, broker-neutral trading data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    client_order_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    fill_price: Decimal
    status: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filled_quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen dataclass: use object.__setattr__ for derived defaults.
        if self.filled_quantity is None:
            object.__setattr__(
                self,
                "filled_quantity",
                self.quantity if self.status == OrderStatus.FILLED.value else Decimal("0"),
            )
        if self.remaining_quantity is None:
            remaining = self.quantity - (self.filled_quantity or Decimal("0"))
            object.__setattr__(self, "remaining_quantity", remaining)


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AccountSnapshot:
    balance: Decimal
    equity: Decimal
    realized_pnl: Decimal
    open_positions: int
    commission_paid: Decimal = Decimal("0")
    daily_realized_pnl: Decimal = Decimal("0")
    daily_commission_paid: Decimal = Decimal("0")
    daily_accounting_available: bool = False
    peak_equity: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")
