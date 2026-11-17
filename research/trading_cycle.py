"""Deterministic, fail-closed 25-minute paper-session decision engine.

This module evaluates timestamped market observations and produces a bounded trade
plan. It deliberately does not submit orders: the current public Deriv feed is still
candidate_unverified, so execution remains blocked until provenance is independently
verified and the paper execution bridge is explicitly integrated.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

SESSION_SECONDS = 25 * 60
PHASE_BUDGET_SECONDS = {
    "discovery": 5 * 60,
    "signal_analysis": 5 * 60,
    "parameter_calculation": 4 * 60,
    "execution_review": 3 * 60,
    "monitoring_and_feedback": 8 * 60,
}
STRATEGY_ID = "jarvis-sma-crossover"
STRATEGY_VERSION = "1.0.0"


def _timestamp(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("market timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite decimal") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field} must be a positive finite decimal")
    return number


def evaluate_25_minute_session(
    observations: Iterable[dict],
    *,
    now: datetime,
    balance: Decimal | str,
    max_risk_fraction: Decimal | str = Decimal("0.005"),
    max_observation_age: timedelta = timedelta(seconds=15),
    kill_switch_enabled: bool = True,
    daily_loss_limit_reached: bool = False,
    session_started_at: datetime | None = None,
) -> dict:
    """Return a deterministic signal/parameter report; never place an order."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    started = _timestamp(session_started_at or now)
    if now < started:
        raise ValueError("session clock cannot precede session start")
    elapsed = (now - started).total_seconds()
    funds = _decimal(balance, "balance")
    risk_fraction = Decimal(str(max_risk_fraction))
    if not risk_fraction.is_finite() or not (Decimal("0") < risk_fraction <= Decimal("0.01")):
        raise ValueError("risk fraction must be greater than 0 and at most 1%")

    normalized = []
    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("each market observation must be an object")
        stamp = _timestamp(item.get("observed_at", ""))
        price = _decimal(item.get("price"), "price")
        normalized.append((stamp, price, item))

    reasons = []
    if len(normalized) < 21:
        reasons.append("insufficient_observations")
    if normalized:
        stamps = [row[0] for row in normalized]
        if len(stamps) != len(set(stamps)):
            reasons.append("duplicate_timestamps")
        if any(b <= a for a, b in zip(stamps, stamps[1:])):
            reasons.append("non_monotonic_timestamps")
        age = now - stamps[-1]
        if age < timedelta(seconds=0):
            reasons.append("future_observation")
        elif age > max_observation_age:
            reasons.append("stale_market_data")
        if any(row[2].get("instrument") != normalized[-1][2].get("instrument") for row in normalized):
            reasons.append("mixed_instruments")
    else:
        reasons.append("missing_market_data")

    prices = [row[1] for row in normalized]
    signal = "none"
    rationale = "No crossover detected."
    entry = stop = target = None
    if len(prices) >= 21 and not any(r in reasons for r in (
        "duplicate_timestamps", "non_monotonic_timestamps", "future_observation",
        "stale_market_data", "mixed_instruments",
    )):
        fast_prev = sum(prices[-6:-1]) / Decimal("5")
        slow_prev = sum(prices[-21:-1]) / Decimal("20")
        fast_now = sum(prices[-5:]) / Decimal("5")
        slow_now = sum(prices[-20:]) / Decimal("20")
        if fast_prev <= slow_prev and fast_now > slow_now:
            signal, rationale = "buy", "Five-observation SMA crossed above twenty-observation SMA."
        elif fast_prev >= slow_prev and fast_now < slow_now:
            signal, rationale = "sell", "Five-observation SMA crossed below twenty-observation SMA."
        if signal != "none":
            entry = prices[-1]
            changes = [abs(b - a) for a, b in zip(prices[-20:], prices[-19:])]
            volatility = sum(changes, Decimal("0")) / Decimal(len(changes))
            stop_distance = max(volatility * Decimal("2"), entry * Decimal("0.001"))
            stop = entry - stop_distance if signal == "buy" else entry + stop_distance
            target = entry + stop_distance * Decimal("2") if signal == "buy" else entry - stop_distance * Decimal("2")
            if stop <= 0:
                signal = "none"
                rationale = "Calculated stop price is invalid; trade rejected."
                entry = stop = target = None

    if kill_switch_enabled:
        reasons.append("kill_switch_enabled")
    if daily_loss_limit_reached:
        reasons.append("daily_loss_limit_reached")
    # This repository has no independent provider attestation verifier yet.
    # Never accept a caller-supplied boolean as proof of provenance.
    reasons.append("market_provenance_unverified")
    if elapsed >= SESSION_SECONDS:
        reasons.append("session_time_budget_exhausted")

    eligible = signal != "none" and not reasons
    source_hash = hashlib.sha256(json.dumps(
        [{
            "observed_at": row[0].isoformat(),
            "price": str(row[1]),
            "instrument": row[2].get("instrument"),
            "source_id": row[2].get("source_id"),
            "provider_event_id": row[2].get("provider_event_id"),
        } for row in normalized],
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "session_status": "within_budget" if elapsed < SESSION_SECONDS else "time_budget_exhausted",
        "session_budget_seconds": SESSION_SECONDS,
        "elapsed_seconds": round(elapsed, 3),
        "phase_budget_seconds": PHASE_BUDGET_SECONDS,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "instrument": normalized[-1][2].get("instrument") if normalized else None,
        "observation_count": len(normalized),
        "latest_observation_at": normalized[-1][0].isoformat() if normalized else None,
        "input_sha256": source_hash,
        "signal": signal,
        "rationale": rationale,
        "trade_parameters": {
            "entry": str(entry) if entry is not None else None,
            "stop_loss": str(stop) if stop is not None else None,
            "take_profit": str(target) if target is not None else None,
            "quantity": None,
            "risk_budget": str(funds * risk_fraction),
            "sizing_status": "BLOCKED_MISSING_CONTRACT_SPECIFICATION",
            "risk_fraction": str(risk_fraction),
            "reward_to_risk": "2",
        },
        "decision": "PAPER_PLAN_ELIGIBLE" if eligible else "NO_TRADE",
        "execution_status": "NOT_EXECUTED",
        "learning_status": "SHADOW_ONLY",
        "block_reasons": sorted(set(reasons)),
        "forward_validation_credit_awarded": False,
        "live_trading_enabled": False,
    }
