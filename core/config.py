"""Strict, dependency-free environment configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _decimal_env(name: str, default: str, *, positive: bool = True) -> Decimal:
    raw = os.getenv(name, default)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal") from exc
    if not value.is_finite() or (positive and value <= 0):
        raise ValueError(f"{name} must be a finite positive number")
    return value


def _int_env(name: str, default: str, *, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its permitted range")
    return value


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
            raise ValueError(
                "Only JARVIS_MODE=paper is implemented. Demo/live adapters are intentionally unavailable."
            )

        # The kill switch cannot be disabled through an environment variable.
        # Releasing it requires an explicit operator action in application code.
        kill_switch = os.getenv("KILL_SWITCH", "true").strip().lower()
        if kill_switch not in {"1", "true", "yes", "on"}:
            raise ValueError("KILL_SWITCH must remain enabled in this foundation release")

        host = os.getenv("STATUS_HOST", "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Status API must bind to localhost until authentication and TLS are configured")

        return cls(
            mode=mode,
            max_stake_per_trade=_decimal_env("MAX_STAKE_PER_TRADE", "5.0"),
            max_daily_loss=_decimal_env("MAX_DAILY_LOSS", "10.0"),
            max_open_positions=_int_env("MAX_OPEN_POSITIONS", "2", minimum=1, maximum=100),
            kill_switch=True,
            status_host=host,
            status_port=_int_env("STATUS_PORT", "8787", minimum=1, maximum=65535),
            starting_balance=_decimal_env("PAPER_STARTING_BALANCE", "10000"),
        )
