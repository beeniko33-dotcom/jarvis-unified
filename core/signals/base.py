"""Signal contract — strategies produce SignalIntent objects, never talk to brokers directly."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.models import Side


@dataclass(frozen=True)
class SignalIntent:
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    confidence: float
    strategy: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("quantity and price must be positive")
