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
        elif "select revision, last_run_id::text" in normalized:
            self.row = self.state.get("integrity_account")
        elif "select run_id::text, revision_before" in normalized:
            self.rows = self.state.get("run_rows", [])
        elif "select sequence, run_id::text" in normalized:
            self.rows = self.state.get("ledger_rows", [])
        elif "select revision, state::text" in normalized:
            self.row = self.state.get("load_row")

    def fetchone(self):
        return self.row

    def fetchall(self):
        return getattr(self, "rows", [])


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
            values["account_id"], input_hash, state_hash, "completed", 1
        )
        self.state["account_row"] = (3,)
        result = self.store.commit_cycle(**values)
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["run_revision"], 1)

    def test_event_type_must_be_a_string(self):
        with self.assertRaisesRegex(ValueError, "safe string event_type"):
            self.store.commit_cycle(**self.cycle(events=[
                {"event_type": 123, "payload": {}},
            ]))

    def test_reused_run_id_with_different_content_is_rejected(self):
        values = self.cycle()
        self.state["prior_run"] = ("other-account", "a" * 64, "b" * 64, "completed", 1)
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

    def test_empty_ledger_verifies_with_genesis_tail(self):
        result = self.store.verify_ledger("paper-account-1")
        self.assertTrue(result["verified"])
        self.assertEqual(result["events"], 0)
        self.assertEqual(result["tail_hash"], "GENESIS")

    def test_remote_ledger_detects_hash_tampering(self):
        run_id = str(uuid4())
        self.state["integrity_account"] = (1, run_id, "a" * 64)
        self.state["run_rows"] = [(run_id, 0, 1, "a" * 64)]
        self.state["ledger_rows"] = [(
            1, run_id, "cycle.completed", self.now,
            {"orders": 0}, "GENESIS", "0" * 64,
        )]
        with self.assertRaisesRegex(PaperStateIntegrityError, "event hash mismatch"):
            self.store.verify_ledger("paper-account-1")

    def test_account_history_requires_contiguous_runs_and_matching_tail(self):
        run_id = str(uuid4())
        self.state["integrity_account"] = (1, run_id, "a" * 64)
        self.state["run_rows"] = [(run_id, 0, 1, "a" * 64)]
        with self.assertRaisesRegex(PaperStateIntegrityError, "no corresponding ledger"):
            self.store.verify_ledger("paper-account-1")

    def test_missing_run_revision_is_rejected(self):
        self.state["integrity_account"] = (2, str(uuid4()), "b" * 64)
        self.state["run_rows"] = [(str(uuid4()), 0, 1, "a" * 64)]
        with self.assertRaisesRegex(PaperStateIntegrityError, "revision does not match"):
            self.store.verify_ledger("paper-account-1")

    def test_wrong_last_run_id_is_rejected(self):
        run_id = str(uuid4())
        self.state["integrity_account"] = (1, str(uuid4()), "a" * 64)
        self.state["run_rows"] = [(run_id, 0, 1, "a" * 64)]
        with self.assertRaisesRegex(PaperStateIntegrityError, "last_run_id"):
            self.store.verify_ledger("paper-account-1")

    def test_orphaned_events_without_account_are_rejected(self):
        self.state["ledger_rows"] = [(1, str(uuid4()), "cycle.completed", self.now,
                                      {}, "GENESIS", "0" * 64)]
        with self.assertRaisesRegex(PaperStateIntegrityError, "without an account"):
            self.store.verify_ledger("paper-account-1")

    def test_load_rejects_non_paper_mode(self):
        self.state["load_row"] = (1, '{"balance":"10"}', "fake", str(uuid4()), "live")
        with self.assertRaises(PaperStateIntegrityError):
            self.store.load_account("paper-account-1")


if __name__ == "__main__":
    unittest.main()
