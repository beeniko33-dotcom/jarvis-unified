from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_paper_cycle_once import (
    load_attested_observation,
    load_operator_controls,
    validate_database_target,
)
from research.gateio_attestation_verifier import VERIFIER_ID


class Cursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.query, self.params = query, params

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, row):
        self.cursor_value = Cursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class RunnerInputTests(unittest.TestCase):
    def test_database_target_requires_exact_isolated_host(self):
        validate_database_target(
            "postgresql://user:password@db.uinibcemffkafdfuewyp.supabase.co:5432/postgres",
            "db.uinibcemffkafdfuewyp.supabase.co",
        )

    def test_database_target_rejects_production_even_if_expected(self):
        with self.assertRaises(ValueError):
            validate_database_target(
                "postgresql://user:password@db.zythldptlplyutphgxpg.supabase.co:5432/postgres",
                "db.zythldptlplyutphgxpg.supabase.co",
            )

    def test_database_target_rejects_mismatch(self):
        with self.assertRaises(ValueError):
            validate_database_target(
                "postgresql://user:password@db.zythldptlplyutphgxpg.supabase.co:5432/postgres",
                "db.uinibcemffkafdfuewyp.supabase.co",
            )

    def test_database_target_accepts_isolated_ipv4_session_pooler(self):
        validate_database_target(
            "postgresql://postgres.uinibcemffkafdfuewyp:password@aws-1-eu-central-1.pooler.supabase.com:5432/postgres",
            "db.uinibcemffkafdfuewyp.supabase.co",
            "uinibcemffkafdfuewyp",
        )

    def test_database_target_rejects_wrong_pooler_project_username(self):
        with self.assertRaises(ValueError):
            validate_database_target(
                "postgresql://postgres.zythldptlplyutphgxpg:password@aws-1-eu-central-1.pooler.supabase.com:5432/postgres",
                "db.uinibcemffkafdfuewyp.supabase.co",
                "uinibcemffkafdfuewyp",
            )

    def test_database_target_rejects_pooler_transaction_mode(self):
        with self.assertRaises(ValueError):
            validate_database_target(
                "postgresql://postgres.uinibcemffkafdfuewyp:password@aws-1-eu-central-1.pooler.supabase.com:6543/postgres",
                "db.uinibcemffkafdfuewyp.supabase.co",
                "uinibcemffkafdfuewyp",
            )

    def test_controls_are_fail_closed_when_missing(self):
        controls = load_operator_controls(
            lambda: Connection(None),
            now=datetime(2026, 11, 19, tzinfo=timezone.utc),
        )
        self.assertIsNone(controls)

    def test_stale_control_heartbeat_engages_both_gates(self):
        now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        controls = load_operator_controls(
            lambda: Connection(("healthy", "paper", False, False,
                                datetime(2026, 11, 19, 11, 50, tzinfo=timezone.utc))),
            now=now,
        )
        self.assertEqual(controls["health"], "stale_or_invalid")
        self.assertTrue(controls["kill_switch_engaged"])
        self.assertTrue(controls["entries_paused"])

    def test_fresh_control_heartbeat_preserves_engaged_kill_switch(self):
        now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        controls = load_operator_controls(
            lambda: Connection(("blocked", "paper", True, True,
                                datetime(2026, 11, 19, 11, 59, tzinfo=timezone.utc))),
            now=now,
        )
        self.assertEqual(controls["health"], "blocked")
        self.assertTrue(controls["kill_switch_engaged"])
        self.assertTrue(controls["entries_paused"])

    def test_observation_requires_exact_verifier_and_no_self_awarded_credit(self):
        payload = {
            "trust_attestation": {"verifier_id": VERIFIER_ID, "signature": "not-verified-here"},
            "provenance_verified": False,
            "evidence_credit": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(load_attested_observation(str(path)), payload)
            payload["evidence_credit"] = True
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_attested_observation(str(path))


if __name__ == "__main__":
    unittest.main()
