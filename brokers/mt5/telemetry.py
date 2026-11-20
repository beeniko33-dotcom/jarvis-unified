"""Fail-closed MT5 quote/heartbeat telemetry models.

This module validates read-only observations only. It has no order methods,
network client, terminal control, or broker credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re


_SYMBOL = re.compile(r"^[A-Z0-9._-]{3,24}$")


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _positive_decimal(value: Decimal, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return value


@dataclass(frozen=True, slots=True)
class MT5Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    observed_at: datetime
    received_at: datetime
    server_id: str
    account_fingerprint: str
    nonce: str

    def validate(
        self,
        *,
        allowed_symbols: frozenset[str],
        expected_server_id: str,
        expected_account_fingerprint: str,
        max_age_seconds: int = 10,
        max_future_skew_seconds: int = 2,
    ) -> "MT5Quote":
        if not _SYMBOL.fullmatch(self.symbol) or self.symbol not in allowed_symbols:
            raise ValueError("symbol is not allowlisted")
        bid = _positive_decimal(self.bid, "bid")
        ask = _positive_decimal(self.ask, "ask")
        if ask < bid:
            raise ValueError("ask must be greater than or equal to bid")
        observed = _aware(self.observed_at, "observed_at")
        received = _aware(self.received_at, "received_at")
        if received < observed:
            age = (received - observed).total_seconds()
        else:
            age = (received - observed).total_seconds()
        if age > max_age_seconds:
            raise ValueError("quote is stale")
        if age < -max_future_skew_seconds:
            raise ValueError("quote timestamp is too far in the future")
        if not self.server_id or self.server_id != expected_server_id:
            raise ValueError("unexpected MT5 server")
        if (
            not self.account_fingerprint
            or self.account_fingerprint != expected_account_fingerprint
        ):
            raise ValueError("unexpected MT5 account binding")
        if not isinstance(self.nonce, str) or not self.nonce.strip() or len(self.nonce) > 128:
            raise ValueError("invalid nonce")
        return self


@dataclass(frozen=True, slots=True)
class MT5Heartbeat:
    server_id: str
    account_fingerprint: str
    terminal_connected: bool
    expert_advisor_version: str
    observed_at: datetime

    def validate(
        self,
        *,
        expected_server_id: str,
        expected_account_fingerprint: str,
        now: datetime,
        max_age_seconds: int = 30,
    ) -> "MT5Heartbeat":
        observed = _aware(self.observed_at, "observed_at")
        current = _aware(now, "now")
        age = (current - observed).total_seconds()
        if age < -2 or age > max_age_seconds:
            raise ValueError("MT5 heartbeat is stale or has an invalid clock")
        if self.server_id != expected_server_id:
            raise ValueError("unexpected MT5 server")
        if self.account_fingerprint != expected_account_fingerprint:
            raise ValueError("unexpected MT5 account binding")
        if self.terminal_connected is not True:
            raise ValueError("MT5 terminal is not connected")
        if not self.expert_advisor_version.strip():
            raise ValueError("missing Expert Advisor version")
        return self
