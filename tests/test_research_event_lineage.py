from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from research.event_lineage import (
    ResearchEvent, ResearchEventLedger, ResearchLineageError, ResearchStage,
)


class ResearchEventLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lineage.sqlite"
        self.ledger = ResearchEventLedger(self.path)
        self.start = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, event_id, stage, seconds, parents=(), payload=None):
        return self.ledger.append(ResearchEvent(
            event_id=event_id, stage=stage,
            occurred_at=self.start + timedelta(seconds=seconds),
            parent_event_ids=tuple(parents), payload=payload or {"value": seconds},
            source_ref="fixture:offline",
        ))

    def full_chain(self):
        self.add("o1", ResearchStage.OBSERVATION, 0)
        self.add("f1", ResearchStage.FEATURE, 1, ("o1",))
        self.add("p1", ResearchStage.FORECAST, 2, ("f1",))
        self.add("d1", ResearchStage.DECISION, 3, ("p1",))
        self.add("r1", ResearchStage.OUTCOME, 4, ("d1",))

    def test_full_lineage_is_durable_and_research_only(self):
        self.full_chain()
        reopened = ResearchEventLedger(self.path)
        self.assertTrue(reopened.verify())
        report = reopened.report()
        self.assertEqual(report["events"], 5)
        self.assertEqual(report["by_stage"]["outcome"], 1)
        self.assertEqual(report["provider_authenticity_verified"], 0)
        self.assertFalse(report["evidence_eligible"])

    def test_duplicate_identical_event_is_idempotent(self):
        first = self.add("o1", ResearchStage.OBSERVATION, 0)
        second = self.add("o1", ResearchStage.OBSERVATION, 0)
        self.assertEqual(first, second)
        self.assertEqual(self.ledger.report()["events"], 1)

    def test_event_id_reuse_with_different_content_is_rejected(self):
        self.add("o1", ResearchStage.OBSERVATION, 0)
        with self.assertRaises(ResearchLineageError):
            self.add("o1", ResearchStage.OBSERVATION, 0, payload={"value": "changed"})

    def test_parent_must_exist(self):
        with self.assertRaises(ResearchLineageError):
            self.add("f1", ResearchStage.FEATURE, 1, ("missing",))

    def test_parent_stage_must_match(self):
        self.add("o1", ResearchStage.OBSERVATION, 0)
        with self.assertRaises(ResearchLineageError):
            self.add("p1", ResearchStage.FORECAST, 1, ("o1",))

    def test_chronology_cannot_go_backwards(self):
        self.add("o1", ResearchStage.OBSERVATION, 5)
        with self.assertRaises(ResearchLineageError):
            self.add("f1", ResearchStage.FEATURE, 4, ("o1",))

    def test_stage_requires_exactly_one_parent(self):
        with self.assertRaises(ResearchLineageError):
            self.add("f1", ResearchStage.FEATURE, 1)

    def test_observation_cannot_have_parent(self):
        with self.assertRaises(ResearchLineageError):
            self.add("o1", ResearchStage.OBSERVATION, 0, ("other",))

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            ResearchEvent("o1", ResearchStage.OBSERVATION, datetime(2026, 1, 1), {})

    def test_secret_like_payload_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            ResearchEvent(
                "o1", ResearchStage.OBSERVATION, self.start,
                {"nested": {"api_token": "do-not-store"}},
            )

    def test_database_rejects_updates_and_deletes(self):
        self.add("o1", ResearchStage.OBSERVATION, 0)
        import sqlite3
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE research_events SET payload_json='{}' WHERE event_id='o1'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM research_events WHERE event_id='o1'")
        self.assertTrue(self.ledger.verify())

    def test_hash_chain_detects_database_tampering(self):
        self.full_chain()
        import sqlite3
        # Simulate an administrator bypassing the ordinary append-only guard.
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER research_events_no_update")
            db.execute("UPDATE research_events SET payload_json='{}' WHERE event_id='f1'")
        self.assertFalse(self.ledger.verify())


if __name__ == "__main__":
    unittest.main()
