"""Deterministic Forex direction forecasts from validated OHLC candles.

This module is analytics-only: it never creates orders, positions, sizing,
entry/exit levels, or broker execution requests. Confidence is a heuristic
strength score, not a calibrated probability of success.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @classmethod
    def from_values(cls, timestamp: datetime, open_: object, high: object,
                    low: object, close: object) -> "Candle":
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            raise ValueError("candle timestamp must be timezone-aware")
        try:
            values = [Decimal(str(v)) for v in (open_, high, low, close)]
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("OHLC values must be valid decimals") from exc
        if any(not v.is_finite() or v <= 0 for v in values):
            raise ValueError("OHLC values must be positive and finite")
        o, h, l, c = values
        if h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("inconsistent OHLC candle")
        return cls(timestamp.astimezone(timezone.utc), o, h, l, c)


@dataclass(frozen=True, slots=True)
class ForexForecast:
    instrument: str
    timeframe: str
    horizon: str
    direction: Direction
    strength_score: int
    data_quality: str
    latest_candle_at: str
    generated_at: str
    rationale: tuple[str, ...]
    disclaimer: str = "Research forecast only; not an instruction to trade."

    def to_dict(self) -> dict:
        result = asdict(self)
        result["direction"] = self.direction.value
        return result


def _ema(values: list[Decimal], period: int) -> Decimal:
    alpha = Decimal(2) / Decimal(period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (Decimal(1) - alpha) * result
    return result


def forecast_direction(
    candles: Iterable[Candle], *, instrument: str, timeframe: str,
    horizon: str = "next candle", now: datetime | None = None,
    max_age: timedelta = timedelta(minutes=15),
) -> ForexForecast:
    """Create a transparent trend/momentum forecast from ordered candles."""
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("instrument is required")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe is required")
    rows = list(candles)
    if len(rows) < 20:
        raise ValueError("at least 20 candles are required")
    if any(not isinstance(row, Candle) for row in rows):
        raise ValueError("all observations must be Candle instances")
    if any(a.timestamp >= b.timestamp for a, b in zip(rows, rows[1:])):
        raise ValueError("candles must be strictly chronological")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("forecast clock must be timezone-aware")
    clock = clock.astimezone(timezone.utc)
    latest = rows[-1]
    age = clock - latest.timestamp
    if age < timedelta(0):
        raise ValueError("latest candle is future-dated")
    if age > max_age:
        raise ValueError("latest candle is stale")

    closes = [row.close for row in rows]
    fast = _ema(closes[-20:], 8)
    slow = _ema(closes[-20:], 20)
    momentum = closes[-1] - closes[-4]
    components = []
    if fast > slow:
        components.append(1)
    elif fast < slow:
        components.append(-1)
    else:
        components.append(0)
    if momentum > 0:
        components.append(1)
    elif momentum < 0:
        components.append(-1)
    else:
        components.append(0)

    score = sum(components)
    direction = (Direction.BULLISH if score == 2 else
                 Direction.BEARISH if score == -2 else Direction.NEUTRAL)
    strength = 50 if score == 0 else 65
    rationale = (
        f"8-period EMA is {'above' if fast > slow else 'below' if fast < slow else 'equal to'} 20-period EMA",
        f"3-candle momentum is {'positive' if momentum > 0 else 'negative' if momentum < 0 else 'flat'}",
    )
    return ForexForecast(
        instrument=instrument.strip().upper(),
        timeframe=timeframe.strip(),
        horizon=horizon,
        direction=direction,
        strength_score=strength,
        data_quality="fresh",
        latest_candle_at=latest.timestamp.isoformat(),
        generated_at=clock.isoformat(),
        rationale=rationale,
    )
