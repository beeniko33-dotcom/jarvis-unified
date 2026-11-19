from __future__ import annotations

from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from research.paper_cycle_engine import _canonical_observation
from research.paper_cycle_orchestrator import run_once
from research.supabase_paper_state import PaperStateConflict

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
_PRIVATE = Ed25519PrivateKey.generate()
PUBLIC_KEY = b64encode(_PRIVATE.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)).decode()


def controls(**changes):
    result = {"health": "healthy", "mode": "paper",
              "kill_switch_engaged": False, "entries_paused": False}
    result.update(changes)
    return result


def observation():
    value = {
        "provider": "Gate.io", "source": "gateio-spot-public-rest-v1",
        "instrument": "BTC_USDT", "interval": "5m", "complete": True,
        "event_time": (NOW - timedelta(seconds=10)).isoformat(),
        "received_at": (NOW - timedelta(seconds=2)).isoformat(),
        "clock_skew_ms": 20, "bid": "90000", "ask": "90001",
        "closes": [str(100 + i * 0.2 + (0.1 if i % 2 else -0.1)) for i in range(50)],
    }
    signature = _PRIVATE.sign(_canonical_observation(value))
    value["trust_attestation"] = {
        "verifier_id": "jarvis-independent-gateio-verifier-v1",
        "signature": b64encode(signature).decode(),
    }
    return value


class FakeStore:
    def __init__(self):
        self.account = None
        self.runs = {}
        self.commits = 0
        self.events = []

    def load_account(self, account_id):
        return deepcopy(self.account)

    def commit_cycle(self, **values):
        prior = self.runs.get(values["run_id"])
        if prior:
            if prior["state"] != values["state"] or prior["input_fingerprint"] != values["input_fingerprint"]:
                raise PaperStateConflict("conflicting deterministic replay")
            return {**prior["result"], "duplicate": True, "revision": self.account["revision"]}
        expected = self.account["revision"] if self.account else 0
        if values["expected_revision"] != expected:
            raise PaperStateConflict("stale revision")
        revision = expected + 1
        result = {"account_id": values["account_id"], "run_id": values["run_id"],
                  "revision": revision, "run_revision": revision,
                  "state_sha256": "a" * 64, "duplicate": False, "mode": "paper"}
        self.account = {"account_id": values["account_id"], "revision": revision,
                        "state": deepcopy(values["state"])}
        self.runs[values["run_id"]] = {
            "state": deepcopy(values["state"]),
            "input_fingerprint": deepcopy(values["input_fingerprint"]),
            "result": result,
        }
        self.events.extend(deepcopy(values["events"]))
        self.commits += 1
        return result


def test_blocked_controls_do_not_write_anything():
    store = FakeStore()
    result = run_once(store=store, account_id="disposable-test",
                      observation=observation(),
                      controls=controls(kill_switch_engaged=True),
                      trusted_verifier_public_key=PUBLIC_KEY, now=NOW)
    assert result["status"] == "blocked"
    assert result["committed"] is False
    assert store.commits == 0
    assert store.events == []


def test_eligible_cycle_commits_research_event_only():
    store = FakeStore()
    result = run_once(store=store, account_id="disposable-test",
                      observation=observation(), controls=controls(),
                      trusted_verifier_public_key=PUBLIC_KEY, now=NOW)
    assert result["status"] == "committed"
    assert result["revision"] == 1
    assert result["duplicate"] is False
    assert store.commits == 1
    assert store.events[0]["event_type"] == "research.decision"
    assert result["order_authorized"] is False
    assert result["orders_submitted"] == 0
    assert result["execution_started"] is False


def test_same_observation_replay_uses_same_run_and_adds_no_event():
    store = FakeStore()
    kwargs = {"store": store, "account_id": "disposable-test",
              "observation": observation(), "controls": controls(),
              "trusted_verifier_public_key": PUBLIC_KEY, "now": NOW}
    first = run_once(**kwargs)
    second = run_once(**kwargs)
    assert first["run_id"] == second["run_id"]
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert store.commits == 1
    assert len(store.events) == 1
