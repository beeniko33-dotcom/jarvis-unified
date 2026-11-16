from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from research.supabase_control_plane import SupabaseControlPlaneStore


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
        if "returning id::text" in normalized:
            self.row = ("audit-event-id",)

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


class SupabaseControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.state = {"queries": [], "params": []}
        self.store = SupabaseControlPlaneStore(
            "postgresql://fake",
            connection_factory=lambda: Connection(self.state),
        )
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

    def test_heartbeat_is_upserted_and_hardcodes_paper_mode(self):
        self.store.record_heartbeat(
            worker_id="collector-1", worker_type="market_collector",
            reported_at=self.now, started_at=self.now - timedelta(minutes=1),
            software_version="dev", git_commit="abc123", health="healthy",
            details={"queue_depth": 2},
        )
        sql = self.state["queries"][0]
        self.assertIn("on conflict (worker_id) do update", sql)
        self.assertIn("'paper'", sql)
        self.assertEqual(self.state["params"][0][0], "collector-1")

    def test_heartbeat_rejects_invalid_health_and_future_start(self):
        with self.assertRaises(ValueError):
            self.store.record_heartbeat(
                worker_id="w", worker_type="collector", reported_at=self.now,
                started_at=None, software_version="dev", git_commit=None,
                health="live", details={},
            )
        with self.assertRaisesRegex(ValueError, "after reported_at"):
            self.store.record_heartbeat(
                worker_id="w", worker_type="collector", reported_at=self.now,
                started_at=self.now + timedelta(seconds=1), software_version="dev",
                git_commit=None, health="healthy",
            )

    def test_audit_event_is_append_only_and_payload_is_hashed(self):
        event_id = self.store.append_audit_event(
            event_type="worker.started", occurred_at=self.now,
            component="collector", payload={"symbol": "EURUSD"},
        )
        self.assertEqual(event_id, "audit-event-id")
        sql = self.state["queries"][0]
        self.assertIn("insert into jarvis_private.runtime_audit_events", sql)
        self.assertNotIn("update", sql)
        self.assertEqual(len(self.state["params"][0][-1]), 64)

    def test_secret_like_payload_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "credential-like"):
            self.store.append_audit_event(
                event_type="worker.started", occurred_at=self.now,
                component="collector", payload={"api_token": "do-not-store"},
            )

    def test_payload_size_and_timezone_are_validated(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.store.append_audit_event(
                event_type="worker.started", occurred_at=datetime(2026, 11, 16),
                component="collector",
            )
        with self.assertRaisesRegex(ValueError, "16 KiB"):
            self.store.append_audit_event(
                event_type="worker.started", occurred_at=self.now,
                component="collector", payload={"data": "x" * 17000},
            )


if __name__ == "__main__":
    unittest.main()
