from __future__ import annotations

from copy import deepcopy

from research.paper_cycle_orchestrator import run_once
from research.supabase_paper_state import PaperStateConflict
from tests.test_paper_cycle_engine import NOW, PUBLIC_KEY, controls, observation


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
        result = {
            "account_id": values["account_id"],
            "run_id": values["run_id"],
            "revision": revision,
            "run_revision": revision,
            "state_sha256": "a" * 64,
            "duplicate": False,
            "mode": "paper",
        }
        self.account = {
            "account_id": values["account_id"],
            "revision": revision,
            "state": deepcopy(values["state"]),
        }
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
    result = run_once(
        store=store, account_id="disposable-test",
        observation=observation(), controls=controls(kill_switch_engaged=True),
        trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
    assert result["status"] == "blocked"
    assert result["committed"] is False
    assert store.commits == 0
    assert store.events == []


def test_eligible_cycle_commits_research_event_only():
    store = FakeStore()
    result = run_once(
        store=store, account_id="disposable-test",
        observation=observation(), controls=controls(),
        trusted_verifier_public_key=PUBLIC_KEY, now=NOW,
    )
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
    kwargs = {
        "store": store, "account_id": "disposable-test",
        "observation": observation(), "controls": controls(),
        "trusted_verifier_public_key": PUBLIC_KEY, "now": NOW,
    }
    first = run_once(**kwargs)
    second = run_once(**kwargs)
    assert first["run_id"] == second["run_id"]
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert store.commits == 1
    assert len(store.events) == 1
