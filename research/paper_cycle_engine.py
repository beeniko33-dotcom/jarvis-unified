"""Deterministic, fail-closed Jarvis paper-cycle decision planner.

This module computes research candidates only. It has no broker, order, wallet,
network, database, or exchange dependencies and cannot execute a trade.
Market trust is accepted only through an Ed25519 attestation verified against
a public key supplied by trusted runtime configuration, never from the payload.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

STRATEGY_ID = "jarvis-gateio-sma-rsi"
STRATEGY_VERSION = "1.0.0"
_SOURCE = "gateio-spot-public-rest-v1"
_SYMBOL = re.compile(r"^[A-Z0-9]{2,15}_USDT$")


def _number(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return result


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 string") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return result.astimezone(timezone.utc)


def _sma(values: list[Decimal], length: int) -> Decimal:
    return sum(values[-length:], Decimal("0")) / Decimal(length)


def _rsi(values: list[Decimal], length: int = 14) -> Decimal:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    window = changes[-length:]
    gains = sum((max(x, Decimal("0")) for x in window), Decimal("0"))
    losses = sum((max(-x, Decimal("0")) for x in window), Decimal("0"))
    if losses == 0:
        return Decimal("100") if gains else Decimal("50")
    return Decimal("100") - (Decimal("100") / (Decimal("1") + gains / losses))


def _canonical_observation(observation: dict[str, Any]) -> bytes:
    # Legacy booleans are deliberately excluded: they are claims, not proof.
    signed_fields = {
        key: value for key, value in observation.items()
        if key not in {"trust_attestation", "provenance_verified", "evidence_credit"}
    }
    return json.dumps(
        signed_fields, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _verify_attestation(
    observation: dict[str, Any], trusted_public_key_b64: str | None
) -> bool:
    if not isinstance(trusted_public_key_b64, str) or not trusted_public_key_b64:
        return False
    attestation = observation.get("trust_attestation")
    if not isinstance(attestation, dict) or not isinstance(attestation.get("verifier_id"), str):
        return False
    if not attestation["verifier_id"].strip():
        return False
    signature_text = attestation.get("signature")
    if not isinstance(signature_text, str):
        return False
    try:
        public_key = base64.b64decode(trusted_public_key_b64, validate=True)
        signature = base64.b64decode(signature_text, validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _canonical_observation(observation)
        )
        return True
    except (ValueError, TypeError, binascii.Error, ImportError):
        return False
    except Exception as exc:  # InvalidSignature is deliberately treated as a failed gate.
        if type(exc).__name__ == "InvalidSignature":
            return False
        raise


def plan_cycle(
    observation: dict[str, Any],
    controls: dict[str, Any] | None,
    *,
    trusted_verifier_public_key: str | None = None,
    now: datetime | None = None,
    max_age_seconds: int = 360,
    max_receive_age_seconds: int = 180,
    max_clock_skew_ms: int = 5000,
) -> dict[str, Any]:
    """Validate one normalized Gate.io snapshot and calculate a non-executable candidate."""
    reasons: list[str] = []
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("planner clock must be timezone-aware")
    current = current.astimezone(timezone.utc)
    if max_age_seconds < 1 or max_receive_age_seconds < 1 or max_clock_skew_ms < 0:
        raise ValueError("age and clock-skew limits are invalid")

    if not isinstance(controls, dict):
        reasons.append("operator_controls_missing")
    else:
        if controls.get("health") != "healthy":
            reasons.append("operator_health_not_healthy")
        if controls.get("mode") != "paper":
            reasons.append("operator_mode_not_paper")
        if controls.get("kill_switch_engaged") is not False:
            reasons.append("kill_switch_blocks_cycle")
        if controls.get("entries_paused") is not False:
            reasons.append("entries_paused")

    try:
        if observation.get("provider") != "Gate.io" or observation.get("source") != _SOURCE:
            reasons.append("unsupported_market_source")
        symbol = observation.get("instrument")
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            reasons.append("unsupported_instrument")
        if observation.get("interval") != "5m":
            reasons.append("unsupported_timeframe")
        if observation.get("complete") is not True:
            reasons.append("candle_not_confirmed_complete")
        if not _verify_attestation(observation, trusted_verifier_public_key):
            reasons.append("independent_provenance_attestation_invalid_or_missing")

        event_time = _time(observation.get("event_time"), "event_time")
        received_at = _time(observation.get("received_at"), "received_at")
        age = (current - event_time).total_seconds()
        receive_age = (current - received_at).total_seconds()
        if event_time > received_at or received_at > current:
            reasons.append("market_timestamps_out_of_order")
        if age < 0 or age > max_age_seconds or receive_age < 0 or receive_age > max_receive_age_seconds:
            reasons.append("market_observation_stale")
        skew = observation.get("clock_skew_ms")
        if isinstance(skew, bool) or not isinstance(skew, int) or abs(skew) > max_clock_skew_ms:
            reasons.append("market_clock_skew_invalid")

        bid = _number(observation.get("bid"), "bid")
        ask = _number(observation.get("ask"), "ask")
        if bid > ask:
            reasons.append("crossed_market_quote")
        closes_raw = observation.get("closes")
        if not isinstance(closes_raw, list) or len(closes_raw) < 50:
            reasons.append("insufficient_candle_history")
            closes: list[Decimal] = []
        else:
            closes = [_number(value, "candle close") for value in closes_raw]
    except (ValueError, TypeError) as exc:
        reasons.append("invalid_market_observation")
        closes = []
        bid = ask = Decimal("0")

    eligible = not reasons
    candidate = "BLOCKED"
    indicators: dict[str, str] = {}
    if eligible:
        fast = _sma(closes, 20)
        slow = _sma(closes, 50)
        rsi = _rsi(closes)
        indicators = {
            "sma20": str(fast.quantize(Decimal("0.00000001"))),
            "sma50": str(slow.quantize(Decimal("0.00000001"))),
            "rsi14": str(rsi.quantize(Decimal("0.00000001"))),
            "bid": str(bid),
            "ask": str(ask),
        }
        if fast > slow and Decimal("50") <= rsi <= Decimal("70"):
            candidate = "LONG_CANDIDATE"
        elif fast < slow or rsi >= Decimal("75"):
            candidate = "EXIT_CANDIDATE"
        else:
            candidate = "HOLD"

    fingerprint_payload = {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "observation": observation,
        "controls": controls,
    }
    return {
        "status": "eligible_for_research_decision" if eligible else "blocked",
        "reasons": reasons,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "candidate": candidate,
        "indicators": indicators,
        "input_fingerprint": _fingerprint(fingerprint_payload),
        "trust_attestation_verified": _verify_attestation(
            observation, trusted_verifier_public_key
        ),
        "mode": "paper",
        "order_authorized": False,
        "orders_submitted": 0,
        "execution_started": False,
    }
