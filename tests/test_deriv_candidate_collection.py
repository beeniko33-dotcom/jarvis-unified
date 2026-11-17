from pathlib import Path
from unittest.mock import patch

from scripts.deriv_forward_candidate_collect import run


def _candidate_report(**overrides):
    report = {
        "observation_count": 12,
        "verified_observation_count": 0,
        "unverified_candidate_count": 12,
        "event_chain_valid": True,
        "level_3_forward_evidence_gate": "BLOCKED_PROVENANCE",
        "level_3_certification": False,
        "trading_actions": 0,
        "account_authentication_used": False,
    }
    report.update(overrides)
    return report


def test_candidate_collection_passes_without_awarding_validation_credit(tmp_path: Path):
    with patch(
        "scripts.deriv_candidate_collect.collect",
        return_value=_candidate_report(),
    ):
        report, status = run(60, tmp_path / "candidate.sqlite3", 10)

    assert status == 0
    assert report["candidate_collection_status"] == "PASS"
    assert report["forward_validation_credit_awarded"] is False
    assert report["provider_provenance_verified"] is False
    assert report["live_trading_enabled"] is False


def test_candidate_collection_fails_closed_for_empty_or_verified_data(tmp_path: Path):
    for changes in (
        {"observation_count": 0, "unverified_candidate_count": 0},
        {"verified_observation_count": 1, "unverified_candidate_count": 11},
        {"event_chain_valid": False},
        {"trading_actions": 1},
    ):
        with patch(
            "scripts.deriv_candidate_collect.collect",
            return_value=_candidate_report(**changes),
        ):
            report, status = run(60, tmp_path / "candidate.sqlite3", 10)
        assert status == 2
        assert report["candidate_collection_status"] == "NO_QUALIFYING_CANDIDATE_DATA"
