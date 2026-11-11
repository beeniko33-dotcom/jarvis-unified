"""Small dependency-free environment configuration loader."""
from __future__ import annotations
import os
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Settings:
    mode: str = "paper"
    max_stake_per_trade: Decimal = Decimal("5.0")
    max_daily_loss: Decimal = Decimal("10.0")
    max_open_positions: int = 2
    kill_switch: bool = True
    status_host: str = "127.0.0.1"
    status_port: int = 8787
    starting_balance: Decimal = Decimal("10000")

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("JARVIS_MODE", "paper").strip().lower()
        if mode != "paper":
            raise ValueError("Only JARVIS_MODE=paper is implemented. Demo/live adapters are intentionally unavailable.")
        host = os.getenv("STATUS_HOST", "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Status API must bind to localhost until authentication and TLS are configured.")
        port = int(os.getenv("STATUS_PORT", "8787"))
        if not 1 <= port <= 65535: raise ValueError("STATUS_PORT must be between 1 and 65535")
        return cls(mode, Decimal(os.getenv("MAX_STAKE_PER_TRADE", "5.0")), Decimal(os.getenv("MAX_DAILY_LOSS", "10.0")), int(os.getenv("MAX_OPEN_POSITIONS", "2")), os.getenv("KILL_SWITCH", "true").lower() in {"1","true","yes","on"}, host, port, Decimal(os.getenv("PAPER_STARTING_BALANCE", "10000")))
