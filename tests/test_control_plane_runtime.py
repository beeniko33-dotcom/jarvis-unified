from __future__ import annotations

import unittest
from datetime import datetime, timezone

from research.control_plane_runtime import ControlPlaneReporter


class FakeStore:
    def __init__(self, *, fail=False):
        self.heartbeats = []
        self.events = []
        self.fail = fail

    def record_heartbeat(self, **kwargs):
        if self.fail:
            raise RuntimeError("sensitive connection detail must not escape")
        self.heartbeats.append(kwargs)

    def append_audit_event(self, **kwargs):
        if self.fail:
            raise RuntimeError("sensitive connection detail must not escape")
        self.events.append(kwargs)
        return "event-id"


class ControlPlaneReporterTests(unittest.TestCase):
    def test_start_and_stop_write_paper_heartbeats_and_audit_events(self):
        store = FakeStore()
        now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        reporter = ControlPlaneReporter(
            store, worker_id="test-status-api", interval_seconds=3600,
            clock=lambda: now,
        )
        reporter.start()
        reporter.stop()

        self.assertEqual([item["health"] for item in store.heartbeats],
                         ["healthy", "stopped"])
        self.assertEqual([item["event_type"] for item in store.events],
                         ["worker.started", "worker.stopped"])
        self.assertTrue(all(item["details"]["mode"] == "paper"
                            for item in store.heartbeats))
        self.assertTrue(all(item["payload"]["mode"] == "paper"
                            for item in store.events))

    def test_database_failures_do_not_raise_or_prevent_shutdown(self):
        reporter = ControlPlaneReporter(
            FakeStore(fail=True), worker_id="offline-test", interval_seconds=3600,
        )
        reporter.start()
        reporter.stop()

    def test_rejects_non_positive_interval(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            ControlPlaneReporter(FakeStore(), interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
