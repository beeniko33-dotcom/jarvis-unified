from __future__ import annotations

import unittest
import threading
import time
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

    def test_session_health_does_not_change_process_heartbeat(self):
        store = FakeStore()
        reporter = ControlPlaneReporter(
            store, worker_id="process-health-test", interval_seconds=3600,
        )
        reporter.start()
        reporter.emit_event("supervisor.session_failed", health="degraded",
                            details={"status": "failed", "exit_code": 2})
        self.assertEqual([item["health"] for item in store.heartbeats], ["healthy"])
        self.assertEqual(store.events[-1]["payload"]["health"], "degraded")
        self.assertEqual(store.heartbeats[-1]["health"], "healthy")
        self.assertTrue(reporter.stop())

    def test_stop_timeout_retains_live_thread_until_it_exits(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingStore(FakeStore):
            heartbeat_calls = 0

            def record_heartbeat(self, **kwargs):
                self.heartbeat_calls += 1
                if self.heartbeat_calls >= 2:
                    entered.set()
                    release.wait(timeout=2)
                super().record_heartbeat(**kwargs)

        store = BlockingStore()
        reporter = ControlPlaneReporter(
            store, worker_id="blocked-stop-test", interval_seconds=0.01,
            shutdown_timeout_seconds=0.05,
        )
        reporter.start()
        self.assertTrue(entered.wait(timeout=1))
        self.assertFalse(reporter.stop())
        self.assertIsNotNone(reporter._thread)
        self.assertTrue(reporter._thread.is_alive())
        release.set()
        self.assertTrue(reporter.stop())
        self.assertIsNone(reporter._thread)
        self.assertFalse(any(
            thread.name == "jarvis-control-plane-heartbeat" and thread.is_alive()
            for thread in threading.enumerate()
        ))

    def test_repeated_start_stop_is_idempotent(self):
        store = FakeStore()
        reporter = ControlPlaneReporter(
            store, worker_id="repeat-test", interval_seconds=3600,
        )
        reporter.start()
        first = reporter._thread
        reporter.start()
        self.assertIs(reporter._thread, first)
        self.assertTrue(reporter.stop())
        self.assertIsNone(reporter._thread)
        reporter.start()
        self.assertIsNotNone(reporter._thread)
        self.assertTrue(reporter.stop())
        self.assertEqual(
            [item["event_type"] for item in store.events],
            ["worker.started", "worker.stopped", "worker.started", "worker.stopped"],
        )

    def test_rejects_non_positive_interval(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            ControlPlaneReporter(FakeStore(), interval_seconds=0)
        with self.assertRaisesRegex(ValueError, "positive"):
            ControlPlaneReporter(FakeStore(), shutdown_timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
