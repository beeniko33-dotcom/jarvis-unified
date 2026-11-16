"""Lifecycle tests for the Biquote collector: reconnect, duplicate delivery,
stale frames and safe shutdown.

The hub is faked at the ``signalrcore`` import boundary so ``collect()`` runs
end to end — the real queue, the real dispatch normalisation and the real
evidence store — without any network access.
"""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research import biquote_feed


def _tick(*, seconds_ago: float = 0.0, mid: str = "1.1000", stale: bool = False) -> dict:
    observed = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    bid = str(float(mid) - 0.0001)
    ask = str(float(mid) + 0.0001)
    return {
        "symbol": "EURUSD",
        "source": "aggregated-public",
        "stale": stale,
        "marketState": "open",
        "quoteAgeSeconds": seconds_ago,
        "timestamp": observed.isoformat(),
        "bid": bid,
        "ask": ask,
        "mid": mid,
    }


class FakeConnection:
    """Minimal stand-in for a signalrcore HubConnection."""

    def __init__(self, frames, *, reconnect_after=None):
        self._frames = frames
        self._reconnect_after = reconnect_after
        self._handlers = {}
        self._open_handlers = []
        self._reconnect_handlers = []
        self._close_handlers = []
        self._error_handlers = []
        self.started = False
        self.stopped = False
        self.subscribe_calls = 0
        self.sent = []

    def on(self, name, handler):
        self._handlers[name] = handler

    def on_open(self, handler):
        self._open_handlers.append(handler)

    def on_reconnect(self, handler):
        self._reconnect_handlers.append(handler)

    def on_close(self, handler):
        self._close_handlers.append(handler)

    def on_error(self, handler):
        self._error_handlers.append(handler)

    def send(self, method, args):
        self.sent.append((method, args))
        if method == "Subscribe":
            self.subscribe_calls += 1

    def start(self):
        self.started = True
        for handler in self._open_handlers:
            handler()
        for index, frame in enumerate(self._frames):
            # signalrcore delivers message.arguments, i.e. a list.
            self._handlers["ReceiveTick"]([frame])
            if self._reconnect_after is not None and index == self._reconnect_after:
                # Reconnect callback records the gap; it must re-subscribe.
                # signalrcore fires on_reconnect after the reconnect
                # handshake; it does not fire on_open a second time.
                for handler in self._reconnect_handlers:
                    handler()

    def stop(self):
        self.stopped = True
        for handler in self._close_handlers:
            handler()


class FakeBuilder:
    def __init__(self, connection):
        self._connection = connection

    def with_url(self, url):
        return self

    def with_automatic_reconnect(self, config):
        return self

    def build(self):
        return self._connection


def _install_fake_signalrcore(connection):
    module = types.ModuleType("signalrcore")
    hub = types.ModuleType("signalrcore.hub_connection_builder")

    class HubConnectionBuilder:
        def __new__(cls):
            return FakeBuilder(connection)

    hub.HubConnectionBuilder = HubConnectionBuilder
    module.hub_connection_builder = hub
    sys.modules["signalrcore"] = module
    sys.modules["signalrcore.hub_connection_builder"] = hub


class CollectorLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "candidates.sqlite3"
        self._saved = {
            name: sys.modules.get(name)
            for name in ("signalrcore", "signalrcore.hub_connection_builder")
        }

    def tearDown(self) -> None:
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def _run(self, frames, *, reconnect_after=None, duration=1):
        connection = FakeConnection(frames, reconnect_after=reconnect_after)
        _install_fake_signalrcore(connection)
        report = biquote_feed.collect(duration, self.db)
        return connection, report

    def test_duplicate_delivery_is_counted_not_double_inserted(self) -> None:
        tick = _tick()
        _, report = self._run([tick, tick, tick])
        self.assertEqual(report["inserted"], 1, report)
        self.assertEqual(report["duplicates"], 2, report)
        self.assertEqual(report["rejected"], 0, report)

    def test_stale_frame_is_rejected(self) -> None:
        _, report = self._run([_tick(seconds_ago=600)])
        self.assertEqual(report["inserted"], 0, report)
        self.assertEqual(report["rejected"], 1, report)

    def test_explicitly_stale_flag_is_rejected(self) -> None:
        _, report = self._run([_tick(stale=True)])
        self.assertEqual(report["inserted"], 0, report)
        self.assertEqual(report["rejected"], 1, report)

    def test_reconnect_resubscribes(self) -> None:
        frames = [_tick(mid="1.1000"), _tick(mid="1.2000"), _tick(mid="1.3000")]
        connection, report = self._run(frames, reconnect_after=0)
        self.assertEqual(
            connection.subscribe_calls, 2,
            "on_reconnect must re-subscribe after a reconnect",
        )
        self.assertEqual(report["inserted"], 3, report)
        self.assertEqual(report["reconnect_events"], 1, report)
        self.assertEqual(report["collection_integrity"], "degraded", report)

    def test_queue_saturation_marks_collection_degraded_and_fails_closed(self) -> None:
        frames = [_tick(mid="1.1010"), _tick(mid="1.1020"), _tick(mid="1.1030")]
        connection = FakeConnection(frames)
        _install_fake_signalrcore(connection)
        with patch.object(biquote_feed, "MAX_PENDING_TICKS", 1):
            report = biquote_feed.collect(1, self.db)

        self.assertEqual(report["received"], 3, report)
        self.assertEqual(report["inserted"], 1, report)
        self.assertEqual(report["dropped_queue_full"], 2, report)
        self.assertEqual(report["collection_integrity"], "degraded", report)
        self.assertEqual(biquote_feed.collection_exit_code(report), 1)

    def test_duplicate_replay_after_restart_is_idempotent(self) -> None:
        tick = _tick(mid="1.1111")
        first_connection, first = self._run([tick])
        self.assertEqual(first["inserted"], 1, first)
        self.assertTrue(first_connection.stopped)

        second_connection, second = self._run([tick])
        self.assertTrue(second_connection.stopped)
        self.assertEqual(second["inserted"], 0, second)
        self.assertEqual(second["duplicates"], 1, second)
        self.assertEqual(second["observation_count"], 1, second)
        self.assertTrue(second["event_chain_valid"], second)

    def test_shutdown_stops_connection_and_drains_queue(self) -> None:
        frames = [_tick(mid=f"1.10{index:02d}") for index in range(5)]
        connection, report = self._run(frames)
        self.assertTrue(connection.stopped, "connection was not stopped")
        self.assertEqual(
            report["inserted"], 5,
            f"ticks lost at shutdown: {report}",
        )
        self.assertTrue(report["event_chain_valid"], report)
        self.assertEqual(report["unexpected_disconnects"], 0, report)

    def test_out_of_order_delivery_is_persisted_as_candidate_without_trust_promotion(self) -> None:
        # Delivery order deliberately differs from source timestamp order.
        frames = [
            _tick(seconds_ago=10, mid="1.1010"),
            _tick(seconds_ago=2, mid="1.1020"),
            _tick(seconds_ago=20, mid="1.1000"),
        ]
        _, report = self._run(frames)
        self.assertEqual(report["inserted"], 3, report)
        self.assertEqual(report["rejected"], 0, report)
        # The append-only chain follows collector ingestion order, not a
        # misleading timestamp sort; retain source timestamps for audit.
        with sqlite3.connect(self.db) as audit_db:
            stored_times = [row[0] for row in audit_db.execute(
                "SELECT observed_at FROM observations ORDER BY id"
            )]
        self.assertGreater(stored_times[0], stored_times[1])
        self.assertLess(stored_times[1], stored_times[2])
        self.assertTrue(report["event_chain_valid"], report)
        self.assertEqual(report["trust_classification"], "candidate_unverified")
        self.assertFalse(report["evidence_credit"])
        self.assertFalse(report["level_3_certification"])

    def test_report_never_grants_evidence_credit(self) -> None:
        _, report = self._run([_tick()])
        self.assertFalse(report["evidence_credit"])
        self.assertFalse(report["level_3_certification"])
        self.assertEqual(report["trust_classification"], "candidate_unverified")
        self.assertEqual(report["trading_actions"], 0)


if __name__ == "__main__":
    unittest.main()
