import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.event_lineage import ResearchEvent, ResearchEventLedger, ResearchStage
from research.execution_observations import ExecutionObservationJournal
from research.observation_lineage_importer import (
    ObservationLineageImportError,
    import_execution_observations,
)


class ObservationLineageImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source_path = root / "execution.sqlite"
        self.destination_path = root / "lineage.sqlite"
        self.source = ExecutionObservationJournal(self.source_path)
        self.destination = ResearchEventLedger(self.destination_path)
        self.when = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_source_events_as_observation_only_and_is_idempotent(self):
        for index in range(3):
            self.source.append(
                event_id=f"paper-event-{index}",
                event_type="risk_approved" if index == 0 else "paper_note",
                data={"client_order_id": f"order-{index}", "index": index},
                occurred_at=self.when,
            )
        first = import_execution_observations(self.source, self.destination, page_size=2)
        second = import_execution_observations(self.source, self.destination, page_size=2)
        self.assertEqual(first.imported, 3)
        self.assertEqual(first.already_present, 0)
        self.assertEqual(second.imported, 0)
        self.assertEqual(second.already_present, 3)
        counts = self.destination.report()["by_stage"]
        self.assertEqual(counts["observation"], 3)
        self.assertEqual(sum(counts.values()), 3)
        self.assertEqual(first.provider_authenticity_verified, 0)
        self.assertFalse(first.evidence_eligible)
        self.assertEqual(first.status, "RESEARCH_ONLY")

    def test_corrupt_source_fails_closed_without_import(self):
        self.source.append(
            event_id="paper-event-1", event_type="risk_rejected",
            data={"client_order_id": "order-1"}, occurred_at=self.when,
        )
        with sqlite3.connect(self.source_path) as db:
            db.execute(
                "UPDATE execution_observations SET payload=? WHERE seq=1",
                ('{"tampered":true}',),
            )
        with self.assertRaises(ObservationLineageImportError):
            import_execution_observations(self.source, self.destination)
        self.assertEqual(self.destination.report()["events"], 0)

    def test_secret_like_payload_is_rejected_by_typed_ledger(self):
        self.source.append(
            event_id="paper-event-secret", event_type="note",
            data={"api_key": "must-not-be-copied"}, occurred_at=self.when,
        )
        with self.assertRaises(ValueError):
            import_execution_observations(self.source, self.destination)
        self.assertEqual(self.destination.report()["events"], 0)

    def test_invalid_page_size_is_rejected(self):
        with self.assertRaises(ValueError):
            import_execution_observations(self.source, self.destination, page_size=0)

    def test_imported_events_are_root_observations(self):
        self.source.append(
            event_id="paper-event-1", event_type="risk_approved",
            data={"client_order_id": "order-1"}, occurred_at=self.when,
        )
        import_execution_observations(self.source, self.destination)
        with self.assertRaises(ValueError):
            self.destination.append(ResearchEvent(
                event_id="bad-feature", stage=ResearchStage.FEATURE,
                occurred_at=self.when, payload={}, parent_event_ids=(),
            ))


if __name__ == "__main__":
    unittest.main()
