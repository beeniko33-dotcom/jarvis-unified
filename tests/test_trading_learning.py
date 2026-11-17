from datetime import datetime, timezone

import pytest

from research.trading_learning import summarize_strategy_outcomes


def rows():
    return [
        {"trade_id": "a", "strategy_id": "sma", "strategy_version": "1",
         "net_pnl": "10", "risk_amount": "5", "closed_at": "2026-11-16T10:00:00+00:00"},
        {"trade_id": "b", "strategy_id": "sma", "strategy_version": "1",
         "net_pnl": "-4", "risk_amount": "5", "closed_at": "2026-11-16T11:00:00+00:00"},
        {"trade_id": "c", "strategy_id": "sma", "strategy_version": "1",
         "net_pnl": "0", "risk_amount": "5", "closed_at": "2026-11-16T12:00:00+00:00"},
    ]


def test_outcome_metrics_and_no_automatic_promotion():
    report = summarize_strategy_outcomes(rows(), minimum_trades=3)
    assert report["closed_trade_count"] == 3
    assert report["wins"] == 1 and report["losses"] == 1
    assert report["breakeven"] == 1
    assert report["net_pnl"] == "6"
    assert report["expectancy_per_trade"] == "2"
    assert report["max_drawdown"] == "4"
    assert report["promotion_status"] == "HUMAN_REVIEW_REQUIRED"
    assert report["automatic_strategy_changes"] is False


def test_reject_duplicate_trade_ids_and_mixed_strategy_versions():
    data = rows()
    data.append(dict(data[0]))
    with pytest.raises(ValueError, match="duplicate"):
        summarize_strategy_outcomes(data)
    data = rows()
    data[1]["strategy_version"] = "2"
    with pytest.raises(ValueError, match="one strategy version"):
        summarize_strategy_outcomes(data)


def test_reject_naive_close_time_and_nonpositive_risk():
    data = rows()
    data[0]["closed_at"] = "2026-11-16T10:00:00"
    with pytest.raises(ValueError, match="timezone"):
        summarize_strategy_outcomes(data)
    data = rows()
    data[0]["risk_amount"] = "0"
    with pytest.raises(ValueError, match="risk_amount"):
        summarize_strategy_outcomes(data)


def test_empty_sample_never_claims_validation():
    report = summarize_strategy_outcomes([], minimum_trades=30)
    assert report["evidence_status"] == "insufficient_sample"
    assert report["promotion_status"] == "HUMAN_REVIEW_REQUIRED"
