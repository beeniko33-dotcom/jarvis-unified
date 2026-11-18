import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ingest_deriv_candidates_to_supabase import (
    build_request_body, ingest_database, load_payloads, post_candidate,
)


def candidate():
    return {
        "observed_at": "2026-11-17T05:00:00+00:00",
        "price": "1.08525",
        "provider_event_id": "frxEURUSD:1794891600:1.08525",
        "raw_message_sha256": "a" * 64,
        "collector_received_at": "2026-11-17T05:00:01+00:00",
        "transport_session_id": "b" * 64,
        "transport_endpoint": "wss://api.derivws.com/trading/v1/options/ws/public",
        "source": "deriv-public-wss-tick-v1",
        "provider": "Deriv",
        "instrument": "EURUSD",
        "strategy_id": "sma-crossover-long",
        "strategy_version": "1.0.0",
        "provenance_verified": False,
        "evidence_credit": False,
        "evidence_class": "unverified_candidate",
    }


def test_request_body_is_candidate_only():
    body = build_request_body(candidate())
    assert body["kind"] == "market_observation"
    assert body["symbol"] == "EURUSD"
    assert body["timeframe"] == "tick"
    assert body["values_json"]["provenance_verified"] is False
    assert body["values_json"]["evidence_credit"] is False
    assert body["values_json"]["evidence_class"] == "unverified_candidate"
    assert "raw_message" not in body["values_json"]


@pytest.mark.parametrize("field,value", [
    ("provider", "Other"),
    ("instrument", "GBPUSD"),
    ("provenance_verified", True),
    ("evidence_credit", True),
    ("evidence_class", "verified"),
])
def test_rejects_mismatched_or_forged_candidate_fields(field, value):
    item = candidate()
    item[field] = value
    with pytest.raises(ValueError):
        build_request_body(item)


def test_post_candidate_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        post_candidate("http://example.test", "not-a-real-key", {})


def test_ingest_database_counts_inserted_and_idempotent_duplicates(tmp_path: Path):
    db_path = tmp_path / "candidate.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT INTO observations(payload) VALUES (?)", (json.dumps(candidate()),))
        db.execute("INSERT INTO observations(payload) VALUES (?)", (json.dumps(candidate()),))
    responses = iter([
        {"ok": True, "inserted": True, "duplicate": False, "provenance": "candidate_unverified"},
        {"ok": True, "inserted": False, "duplicate": True, "provenance": "candidate_unverified"},
    ])
    with patch(
        "scripts.ingest_deriv_candidates_to_supabase.post_candidate",
        side_effect=lambda *args: next(responses),
    ):
        result = ingest_database(db_path, "https://example.supabase.co", "secret-not-printed")
    assert result["observations_submitted"] == 2
    assert result["inserted"] == 1
    assert result["duplicates"] == 1
    assert result["forward_validation_credit_awarded"] is False

def test_post_candidate_sends_secret_key_only_in_apikey_header():
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "ok": True,
                "inserted": True,
                "duplicate": False,
                "provenance": "candidate_unverified",
            }).encode()

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        result = post_candidate(
            "https://example.supabase.co",
            "secret-api-key-not-printed",
            build_request_body(candidate()),
        )

    request = urlopen.call_args.args[0]
    assert request.get_header("Apikey") == "secret-api-key-not-printed"
    assert request.get_header("Authorization") is None
    assert result["ok"] is True
