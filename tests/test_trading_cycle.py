from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from research.trading_cycle import evaluate_25_minute_session


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def ticks():
    return [
        {"observed_at": (NOW - timedelta(seconds=20-i)).isoformat(),
         "price": str(Decimal("1.1000") + Decimal(i) * Decimal("0.0001")),
         "instrument": "EURUSD"}
        for i in range(21)
    ]


def test_25_minute_budget_and_explicit_phase_allocations():
    report = evaluate_25_minute_session(ticks(), now=NOW, balance="10000")
    assert report["session_budget_seconds"] == 1500
    assert sum(report["phase_budget_seconds"].values()) == 1500
    assert report["execution_status"] == "NOT_EXECUTED"


def test_unverified_feed_never_becomes_execution_eligible():
    report = evaluate_25_minute_session(
        ticks(), now=NOW, balance="10000", provenance_verified=False,
        kill_switch_enabled=False,
    )
    assert report["decision"] == "NO_TRADE"
    assert "market_provenance_unverified" in report["block_reasons"]
    assert report["execution_status"] == "NOT_EXECUTED"


def test_kill_switch_and_daily_loss_block_entry_even_with_verified_feed():
    report = evaluate_25_minute_session(
        ticks(), now=NOW, balance="10000", provenance_verified=True,
        kill_switch_enabled=True, daily_loss_limit_reached=True,
    )
    assert report["decision"] == "NO_TRADE"
    assert "kill_switch_enabled" in report["block_reasons"]
    assert "daily_loss_limit_reached" in report["block_reasons"]


def test_stale_future_duplicate_and_missing_data_fail_closed():
    stale = [{"observed_at": (NOW-timedelta(minutes=1)).isoformat(),
              "price": "1.1", "instrument": "EURUSD"}] * 21
    report = evaluate_25_minute_session(stale, now=NOW, balance="10000")
    assert "stale_market_data" in report["block_reasons"]
    future = ticks()
    future[-1] = {**future[-1], "observed_at": (NOW+timedelta(seconds=1)).isoformat()}
    assert "future_observation" in evaluate_25_minute_session(
        future, now=NOW, balance="10000"
    )["block_reasons"]
    duplicate = ticks()
    duplicate[-1] = duplicate[-2]
    assert "duplicate_timestamps" in evaluate_25_minute_session(
        duplicate, now=NOW, balance="10000"
    )["block_reasons"]
    assert "missing_market_data" in evaluate_25_minute_session(
        [], now=NOW, balance="10000"
    )["block_reasons"]


def test_elapsed_time_exhaustion_blocks_trade():
    started = NOW - timedelta(seconds=1500)
    report = evaluate_25_minute_session(
        ticks(), now=NOW, balance="10000", session_started_at=started,
        provenance_verified=True, kill_switch_enabled=False,
    )
    assert report["decision"] == "NO_TRADE"
    assert "session_time_budget_exhausted" in report["block_reasons"]


def test_bad_risk_fraction_is_rejected():
    with pytest.raises(ValueError):
        evaluate_25_minute_session(ticks(), now=NOW, balance="10000",
                                   max_risk_fraction="0.02")
