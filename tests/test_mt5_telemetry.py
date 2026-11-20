from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from brokers.mt5.telemetry import MT5Heartbeat, MT5Quote


NOW = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)


def quote(**overrides):
    values = dict(
        symbol="EURUSD",
        bid=Decimal("1.08001"),
        ask=Decimal("1.08013"),
        observed_at=NOW - timedelta(seconds=1),
        received_at=NOW,
        server_id="Deriv-Demo",
        account_fingerprint="acct-fp-123",
        nonce="one-time-nonce",
    )
    values.update(overrides)
    return MT5Quote(**values)


def validate(item):
    return item.validate(
        allowed_symbols=frozenset({"EURUSD", "GBPUSD"}),
        expected_server_id="Deriv-Demo",
        expected_account_fingerprint="acct-fp-123",
    )


def test_accepts_fresh_allowlisted_quote_with_bound_account():
    assert validate(quote()).symbol == "EURUSD"


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "BTCUSDT"},
        {"ask": Decimal("1.07999")},
        {"bid": Decimal("0")},
        {"server_id": "Other-Server"},
        {"account_fingerprint": "different-account"},
        {"nonce": " "},
        {"observed_at": NOW - timedelta(seconds=30)},
        {"observed_at": NOW + timedelta(seconds=10)},
        {"observed_at": datetime(2026, 11, 20, 20, 0)},
    ],
)
def test_rejects_untrusted_or_invalid_quotes(changes):
    with pytest.raises(ValueError):
        validate(quote(**changes))


def test_rejects_float_prices_and_nonfinite_prices():
    with pytest.raises(ValueError):
        validate(quote(bid=1.08))
    with pytest.raises(ValueError):
        validate(quote(ask=Decimal("NaN")))


def test_accepts_fresh_connected_heartbeat():
    item = MT5Heartbeat(
        server_id="Deriv-Demo",
        account_fingerprint="acct-fp-123",
        terminal_connected=True,
        expert_advisor_version="0.1.0",
        observed_at=NOW - timedelta(seconds=2),
    )
    assert item.validate(
        expected_server_id="Deriv-Demo",
        expected_account_fingerprint="acct-fp-123",
        now=NOW,
    ).terminal_connected


@pytest.mark.parametrize(
    "changes",
    [
        {"server_id": "wrong"},
        {"account_fingerprint": "wrong"},
        {"terminal_connected": False},
        {"observed_at": NOW - timedelta(minutes=5)},
        {"expert_advisor_version": ""},
    ],
)
def test_heartbeat_fails_closed(changes):
    values = dict(
        server_id="Deriv-Demo",
        account_fingerprint="acct-fp-123",
        terminal_connected=True,
        expert_advisor_version="0.1.0",
        observed_at=NOW,
    )
    values.update(changes)
    item = MT5Heartbeat(**values)
    with pytest.raises(ValueError):
        item.validate(
            expected_server_id="Deriv-Demo",
            expected_account_fingerprint="acct-fp-123",
            now=NOW,
        )
