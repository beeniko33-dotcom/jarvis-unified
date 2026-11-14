import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.execution_observations import (
    ExecutionObservationJournal,
    ObservationConflictError,
)


class ExecutionObservationJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "observations.sqlite"
        self.journal = ExecutionObservationJournal(self.path)
        self.when = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_verify(self):
        digest = self.journal.append(
            event_id="decision-1",
            event_type="risk_rejected",
            data={"reason": "kill switch engaged", "strategy_version": None},
            occurred_at=self.when,
        )
        self.assertEqual(len(digest), 64)
        self.assertTrue(self.journal.verify())
        event = self.journal.list_events()[0]
        self.assertEqual(event["data"]["strategy_version"], None)
        self.assertEqual(event["data"]["reason"], "kill switch engaged")

    def test_duplicate_is_idempotent(self):
        args = dict(
            event_id="decision-1", event_type="risk_approved",
            data={"symbol": "EURUSD"}, occurred_at=self.when,
        )
        first = self.journal.append(**args)
        second = self.journal.append(**args)
        self.assertEqual(first, second)
        self.assertEqual(len(self.journal.list_events()), 1)

    def test_reused_id_with_different_content_is_rejected(self):
        self.journal.append(
            event_id="decision-1", event_type="risk_rejected",
            data={"reason": "one"}, occurred_at=self.when,
        )
        with self.assertRaises(ObservationConflictError):
            self.journal.append(
                event_id="decision-1", event_type="risk_rejected",
                data={"reason": "two"}, occurred_at=self.when,
            )

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            self.journal.append(
                event_id="decision-1", event_type="risk_rejected",
                data={}, occurred_at=datetime(2026, 11, 14),
            )

    def test_tampering_is_detected(self):
        self.journal.append(
            event_id="decision-1", event_type="risk_rejected",
            data={"reason": "original"}, occurred_at=self.when,
        )
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE execution_observations SET payload=? WHERE event_id=?",
                ('{"tampered":true}', "decision-1"),
            )
        self.assertFalse(self.journal.verify())

    def test_limit_is_validated(self):
        with self.assertRaises(ValueError):
            self.journal.list_events(limit=0)


if __name__ == "__main__":
    unittest.main()
