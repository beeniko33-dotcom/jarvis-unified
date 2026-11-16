from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from research.supabase_paper_state import (
    PaperStateConflict, PaperStateIntegrityError, SupabasePaperStateStore,
)


class Cursor:
    def __init__(self, state):
        self.state = state
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.state["queries"].append(normalized)
        self.state["params"].append(params)
        if "select revision from jarvis_private.paper_accounts" in normalized:
            self.row = self.state.get("account_row")
        elif "select account_id, input_sha256" in normalized:
            self.row = self.state.get("prior_run")
        elif "select sequence, event_hash" in normalized:
            self.row = self.state.get("ledger_tail")
        elif "select revision, state::text" in normalized:
            self.row = self.state.get("load_row")

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return Cursor(self.state)

    def close(self):
        pass


class SupabasePaperStateTests(unittest.TestCase):
    def setUp(self):
        self.state = {"queries": [], "params": []}
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        self.store = SupabasePaperStateStore(
            "postgresql://fake", connection_factory=lambda: Connection(self.state),
            clock=lambda: self.now,
        )

    def cycle(self, **overrides):
        values = {
            "account_id": "paper-account-1",
            "run_id": str(uuid4()),
            "expected_revision": 0,
            "state": {"balance": "10000.00", "positions": []},
            "events": [{"event_type": "cycle.completed", "payload": {"orders": 0}}],
            "input_fingerprint": {"market_snapshot": "sha256:abc", "strategy_version": "1.0"},
        }
        values.update(overrides)
        return values

    def test_cycle_commit_is_paper_only_and_transactional(self):
        result = self.store.commit_cycle(**self.cycle())
        self.assertEqual(result["revision"], 1)
        self.assertFalse(result["duplicate"])
        sql = self.state["queries"]
        self.assertTrue(any("pg_advisory_xact_lock" in q for q in sql))
        self.assertTrue(any("for update" in q for q in sql))
        self.assertTrue(any("insert into jarvis_private.paper_runs" in q for q in sql))
        self.assertTrue(any("insert into jarvis_private.paper_ledger_events" in q for q in sql))
        self.assertTrue(any("insert into jarvis_private.paper_accounts" in q for q in sql))
        self.assertTrue(any("'paper', 'completed'" in q for q in sql if "insert into jarvis_private.paper_runs" in q))
        self.assertTrue(any("'paper'" in q for q in sql if "insert into jarvis_private.paper_accounts" in q))

    def test_stale_revision_is_rejected(self):
        self.state["account_row"] = (4,)
        with self.assertRaises(PaperStateConflict):
            self.store.commit_cycle(**self.cycle(expected_revision=3))

    def test_duplicate_run_is_idempotent(self):
        values = self.cycle()
        import hashlib, json
        encoded = json.dumps(values["input_fingerprint"], sort_keys=True, separators=(",", ":"))
        input_hash = hashlib.sha256(encoded.encode()).hexdigest()
        encoded_state = json.dumps(values["state"], sort_keys=True, separators=(",", ":"))
        state_hash = hashlib.sha256(encoded_state.encode()).hexdigest()
        self.state["prior_run"] = (
            values["account_id"], input_hash, state_hash, "completed"
        )
        result = self.store.commit_cycle(**values)
        self.assertTrue(result["duplicate"])

    def test_reused_run_id_with_different_content_is_rejected(self):
        values = self.cycle()
        self.state["prior_run"] = ("other-account", "a" * 64, "b" * 64, "completed")
        with self.assertRaises(PaperStateConflict):
            self.store.commit_cycle(**values)

    def test_credentials_are_rejected_from_state_and_metadata(self):
        with self.assertRaisesRegex(ValueError, "credential-like"):
            self.store.commit_cycle(**self.cycle(state={"api_token": "never"}))
        with self.assertRaisesRegex(ValueError, "credential-like"):
            self.store.commit_cycle(**self.cycle(metadata={"password": "never"}))

    def test_invalid_payload_and_naive_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.commit_cycle(**self.cycle(events=[]))
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.store.commit_cycle(**self.cycle(events=[{
                "event_type": "cycle.completed",
                "occurred_at": datetime(2026, 11, 16),
                "payload": {},
            }]))

    def test_load_detects_tampered_snapshot(self):
        self.state["load_row"] = (2, '{"balance":"10"}', "0" * 64, str(uuid4()), "paper")
        with self.assertRaises(PaperStateIntegrityError):
            self.store.load_account("paper-account-1")

    def test_load_rejects_non_paper_mode(self):
        self.state["load_row"] = (1, '{"balance":"10"}', "fake", str(uuid4()), "live")
        with self.assertRaises(PaperStateIntegrityError):
            self.store.load_account("paper-account-1")


if __name__ == "__main__":
    unittest.main()
