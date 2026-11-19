from base64 import b64encode
from datetime import datetime, timedelta, timezone
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from research.paper_cycle_engine import _canonical_observation, plan_cycle

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
PRIVATE_KEY = Ed25519PrivateKey.generate()
PUBLIC_KEY = b64encode(
    PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode()


def controls(**changes):
    value = {
        "health": "healthy",
        "mode": "paper",
        "kill_switch_engaged": False,
        "entries_paused": False,
    }
    value.update(changes)
    return value


def observation(**changes):
    base = {
        "provider": "Gate.io",
        "source": "gateio-spot-public-rest-v1",
        "instrument": "BTC_USDT",
        "interval": "5m",
        "complete": True,
        "event_time": (NOW - timedelta(seconds=10)).isoformat(),
        "received_at": (NOW - timedelta(seconds=2)).isoformat(),
        "clock_skew_ms": 20,
        "bid": "90000.00",
        "ask": "90001.00",
        "closes": [str(100 + i * 0.2 + (0.1 if i % 2 else -0.1)) for i in range(50)],
        # These legacy booleans are not accepted as provenance proof.
        "provenance_verified": True,
        "evidence_credit": True,
    }
    base.update(changes)
    return sign_observation(base)


def sign_observation(value):
    unsigned = dict(value)
    unsigned.pop("trust_attestation", None)
    signature = PRIVATE_KEY.sign(_canonical_observation(unsigned))
    value["trust_attestation"] = {
        "verifier_id": "jarvis-independent-gateio-verifier-v1",
        "signature": b64encode(signature).decode(),
    }
    return value


def test_verified_market_and_controls_produce_research_candidate_only():
    result = plan_cycle(
        observation(), controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    assert result["status"] == "eligible_for_research_decision"
    assert result["candidate"] in {"LONG_CANDIDATE", "EXIT_CANDIDATE", "HOLD"}
    assert result["trust_attestation_verified"] is True
    assert result["order_authorized"] is False
    assert result["orders_submitted"] == 0
    assert result["execution_started"] is False
    assert result["input_fingerprint"]


@pytest.mark.parametrize(
    ("control_change", "reason"),
    [
        ({"kill_switch_engaged": True}, "kill_switch_blocks_cycle"),
        ({"entries_paused": True}, "entries_paused"),
        ({"health": "blocked"}, "operator_health_not_healthy"),
        ({"mode": "live"}, "operator_mode_not_paper"),
    ],
)
def test_operator_controls_fail_closed(control_change, reason):
    result = plan_cycle(
        observation(), controls(**control_change),
        trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
    assert result["status"] == "blocked"
    assert reason in result["reasons"]
    assert result["candidate"] == "BLOCKED"
    assert result["order_authorized"] is False


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"complete": False}, "candle_not_confirmed_complete"),
        ({"source": "unknown"}, "unsupported_market_source"),
        ({"interval": "1m"}, "unsupported_timeframe"),
        ({"instrument": "BTC_USD"}, "unsupported_instrument"),
        ({"bid": "90002", "ask": "90001"}, "crossed_market_quote"),
        ({"clock_skew_ms": 9000}, "market_clock_skew_invalid"),
        ({"closes": [1, 2]}, "insufficient_candle_history"),
    ],
)
def test_malformed_market_data_blocks(change, reason):
    result = plan_cycle(
        observation(**change), controls(),
        trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
    assert result["status"] == "blocked"
    assert reason in result["reasons"]
    assert result["orders_submitted"] == 0


def test_recent_completed_five_minute_candle_remains_eligible():
    event = NOW - timedelta(seconds=240)
    result = plan_cycle(
        observation(event_time=event.isoformat()), controls(),
        trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
    assert result["status"] == "eligible_for_research_decision"


def test_stale_observation_blocks():
    old = NOW - timedelta(minutes=10)
    result = plan_cycle(
        observation(event_time=old.isoformat(), received_at=old.isoformat()),
        controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
    assert "market_observation_stale" in result["reasons"]


def test_missing_controls_block():
    result = plan_cycle(
        observation(), None, trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    assert result["status"] == "blocked"
    assert "operator_controls_missing" in result["reasons"]


def test_input_fingerprint_is_deterministic():
    first = plan_cycle(
        observation(), controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    second = plan_cycle(
        observation(), controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    assert first["input_fingerprint"] == second["input_fingerprint"]


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        plan_cycle(observation(), controls(), now=datetime(2026, 11, 19, 12))


def test_boolean_provenance_claims_without_signature_are_rejected():
    value = observation()
    value.pop("trust_attestation")
    result = plan_cycle(
        value, controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    assert "independent_provenance_attestation_invalid_or_missing" in result["reasons"]
    assert result["trust_attestation_verified"] is False


def test_tampering_after_attestation_is_rejected():
    value = observation()
    value["bid"] = "1"
    result = plan_cycle(
        value, controls(), trusted_verifier_public_key=PUBLIC_KEY, now=NOW
    )
    assert result["status"] == "blocked"
    assert "independent_provenance_attestation_invalid_or_missing" in result["reasons"]


def test_payload_cannot_choose_its_own_trusted_key():
    value = observation()
    value["trusted_public_key"] = PUBLIC_KEY
    result = plan_cycle(value, controls(), now=NOW)
    assert result["status"] == "blocked"
    assert "independent_provenance_attestation_invalid_or_missing" in result["reasons"]
