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
