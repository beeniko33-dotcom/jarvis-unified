import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.execution_observations import ExecutionObservationJournal
from research.paper_reflection_bridge import (
    PaperReflectionBridgeError,
    build_paper_reflections,
)
from research.reflection import ReflectionStore


class PaperReflectionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.journal_path = root / "learning.sqlite"
        self.reflection_path = root / "reflections.sqlite"
        self.journal = ExecutionObservationJournal(self.journal_path)
        self.store = ReflectionStore(self.reflection_path)
        self.day_one = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        self.day_two = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bridges_all_event_classes_and_keeps_source_links(self):
        self.journal.append(
            event_id="risk-1", event_type="risk_rejected",
            data={"symbol": "EURUSD", "reason": "daily_loss_limit"},
            occurred_at=self.day_one,
        )
        self.journal.append(
            event_id="broker-1", event_type="broker_order_result",
            data={"symbol": "EURUSD", "side": "buy", "result_status": "filled",
                  "filled_quantity": "0.1", "order_id": "order-1"},
            occurred_at=self.day_one,
        )
        self.journal.append(
            event_id="close-1", event_type="position_close_result",
            data={"symbol": "EURUSD", "realized_delta": "-2.5",
                  "commission_delta": "0.2"},
            occurred_at=self.day_two,
        )
        self.journal.append(
            event_id="ledger-1", event_type="paper_ledger_event",
            data={"source_ledger_id": "ledger-hash", "source_event_type": "paper_close",
                  "source_event_seq": 4, "source_created_at": "2026-11-10T13:00:00+00:00",
                  "source_utc_day": "2026-11-10", "realized_delta": "-1.25",
                  "commission_delta": "0.1"},
            occurred_at=self.day_two,
        )
        reflections = build_paper_reflections(self.journal, self.store)
        self.assertEqual(len(reflections), 3)
        all_facts = [fact for item in reflections for fact in item.facts]
        self.assertEqual({fact["event_id"] for fact in all_facts},
                         {"risk-1", "broker-1", "close-1", "ledger-1"})
        self.assertTrue(all(fact["source_ref"].startswith("learning-journal:") for fact in all_facts))
        self.assertTrue(all(fact["provenance"] == "not_applicable" for fact in all_facts))
        ledger_fact = next(fact for fact in all_facts if fact["event_id"] == "ledger-1")
        self.assertIn("paper ledger paper_close", ledger_fact["statement"])
        self.assertIn("realized_delta=-1.25", ledger_fact["statement"])

    def test_reflection_preserves_explicit_strategy_and_experiment_metadata(self):
        self.journal.append(
            event_id="decision-1", event_type="risk_approved",
            data={
                "client_order_id": "client-1",
                "strategy_id": "sma-reference",
                "strategy_version": "2.1",
                "strategy_config_hash": "a" * 64,
                "experiment_id": "experiment-123",
                "quote_source": "deriv-candidate",
                "quote_timestamp": "2026-11-10T12:00:00+00:00",
                "metadata": {"signal_id": "signal-77", "signal_type": "entry"},
            },
            occurred_at=self.day_one,
        )
        reflection = build_paper_reflections(self.journal, self.store)[0]
        statement = reflection.facts[0]["statement"]
        self.assertIn("strategy_id=sma-reference", statement)
        self.assertIn("strategy_version=2.1", statement)
        self.assertIn("experiment_id=experiment-123", statement)
        self.assertIn("signal_id=signal-77", statement)
        self.assertIn("quote_source=deriv-candidate", statement)

    def test_replay_is_idempotent_and_does_not_duplicate_reflections(self):
        self.journal.append(
            event_id="risk-1", event_type="risk_approved",
            data={"symbol": "EURUSD"}, occurred_at=self.day_one,
        )
        first = build_paper_reflections(self.journal, self.store)
        second = build_paper_reflections(self.journal, self.store)
        self.assertEqual(first[0].reflection_id, second[0].reflection_id)
        self.assertEqual(len(self.store.list_for_session(first[0].session_id)), 1)

    def test_distinct_source_ledgers_are_not_combined(self):
        for event_id, source_id in (("a", "ledger-a"), ("b", "ledger-b")):
            self.journal.append(
                event_id=event_id, event_type="paper_ledger_event",
                data={"source_ledger_id": source_id, "source_event_type": "paper_order",
                      "source_created_at": "2026-11-10T12:00:00+00:00"},
                occurred_at=self.day_one,
            )
        reflections = build_paper_reflections(self.journal, self.store)
        self.assertEqual(len(reflections), 2)
        self.assertNotEqual(reflections[0].session_id, reflections[1].session_id)

    def test_invalid_journal_is_rejected(self):
        self.journal.append(
            event_id="risk-1", event_type="risk_approved", data={},
            occurred_at=self.day_one,
        )
        with sqlite3.connect(self.journal_path) as db:
            db.execute("UPDATE execution_observations SET payload='{}' WHERE event_id='risk-1'")
        with self.assertRaises(PaperReflectionBridgeError):
            build_paper_reflections(self.journal, self.store)


if __name__ == "__main__":
    unittest.main()
