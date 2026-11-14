import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.models import OrderRequest, Side
from research.execution_observations import ExecutionObservationJournal
from research.paper_reflection_bridge import build_paper_reflections
from research.reflection import ReflectionStore
from research.paper_ledger_importer import (
    PaperLedgerImportError,
    import_paper_ledger,
)


class PaperLedgerImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "paper.sqlite"
        self.journal = ExecutionObservationJournal(self.root / "learning.sqlite")
        self.broker = PersistentPaperBroker(
            Decimal("1000"),
            database_path=self.source,
            commission_per_side=Decimal("0.1"),
            clock=lambda: datetime(2026, 11, 14, 12, tzinfo=timezone.utc),
        )
        self.broker.place_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "entry-1")
        )
        self.broker.set_last_price("EURUSD", Decimal("8"))
        self.broker.close_position("EURUSD", Decimal("8"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_verified_ledger_read_only_and_idempotently(self):
        before_count = self.broker.ledger_event_count()
        first = import_paper_ledger(self.source, self.journal)
        self.assertTrue(first.source_chain_verified)
        self.assertEqual(first.source_events, before_count)
        self.assertEqual(first.imported_events, before_count)
        self.assertEqual(first.skipped_events, 0)
        self.assertEqual(self.broker.ledger_event_count(), before_count)
        self.assertTrue(self.broker.verify_ledger())
        self.assertTrue(self.journal.verify())

        second = import_paper_ledger(self.source, self.journal)
        self.assertEqual(second.imported_events, 0)
        self.assertEqual(second.skipped_events, before_count)
        self.assertEqual(len(self.journal.list_events()), before_count)

    def test_preserves_loss_and_cost_deltas_without_netting_them_away(self):
        import_paper_ledger(self.source, self.journal)
        events = self.journal.list_events(limit=100)
        close = next(
            event for event in events
            if event["data"]["source_event_type"] == "paper_close"
        )
        self.assertLess(Decimal(close["data"]["realized_delta"]), Decimal("0"))
        self.assertGreater(Decimal(close["data"]["commission_delta"]), Decimal("0"))
        self.assertTrue(close["data"]["source_event_hash"])
        snapshot = close["data"]["account_snapshot"]
        self.assertEqual(snapshot["commission_per_side"], "0.1")
        self.assertEqual(snapshot["balance"] is not None, True)

    def test_corrupt_source_chain_is_rejected_before_any_import(self):
        with sqlite3.connect(self.source) as db:
            db.execute(
                "UPDATE paper_events SET payload=? WHERE seq=2",
                ('{"tampered":true}',),
            )
        with self.assertRaises(PaperLedgerImportError):
            import_paper_ledger(self.source, self.journal)
        self.assertEqual(self.journal.list_events(), [])

    def test_snapshot_tail_mismatch_is_rejected_before_any_import(self):
        with sqlite3.connect(self.source) as db:
            db.execute(
                "UPDATE paper_state SET payload=? WHERE singleton=1",
                ('{"balance":"999"}',),
            )
        with self.assertRaises(PaperLedgerImportError):
            import_paper_ledger(self.source, self.journal)
        self.assertEqual(self.journal.list_events(), [])

    def test_missing_source_is_rejected(self):
        with self.assertRaises(PaperLedgerImportError):
            import_paper_ledger(self.root / "missing.sqlite", self.journal)


    def test_research_lineage_survives_restart_import_and_reflection_without_secrets(self):
        metadata = {
            "research_lineage": {
                "strategy_id": "momentum-v2",
                "strategy_version": "2.1",
                "strategy_config_hash": "a" * 64,
                "experiment_id": "exp-2026-11",
                "data_hash": "b" * 64,
            },
            "api_key": "must-not-persist",
        }
        broker = PersistentPaperBroker(
            Decimal("1000"), database_path=self.root / "lineage.sqlite"
        )
        result = broker.place_order(
            OrderRequest("SOLUSD", Side.BUY, Decimal("1"), Decimal("100"), "lineage-1",
                         metadata=metadata)
        )
        self.assertEqual(result.metadata["research_lineage"]["strategy_id"], "momentum-v2")
        self.assertNotIn("api_key", result.metadata)

        restored = PersistentPaperBroker(
            Decimal("1000"), database_path=self.root / "lineage.sqlite"
        )
        self.assertEqual(
            restored._orders[result.order_id].metadata["research_lineage"]["experiment_id"],
            "exp-2026-11",
        )
        self.assertTrue(restored.verify_ledger())

        journal = ExecutionObservationJournal(self.root / "lineage-learning.sqlite")
        import_paper_ledger(self.root / "lineage.sqlite", journal)
        reflections = build_paper_reflections(
            journal, ReflectionStore(self.root / "lineage-reflections.sqlite")
        )
        statements = " ".join(fact["statement"] for item in reflections for fact in item.facts)
        self.assertIn("strategy_id=momentum-v2", statements)
        self.assertIn("experiment_id=exp-2026-11", statements)
        self.assertIn("strategy_config_hash=" + "a" * 64, statements)
        self.assertNotIn("must-not-persist", statements)

    def test_working_order_lineage_survives_partial_fill_and_restart(self):
        broker = PersistentPaperBroker(
            Decimal("1000"), database_path=self.root / "working-lineage.sqlite"
        )
        opened = broker.place_working_order(
            OrderRequest(
                "SOLUSD", Side.BUY, Decimal("2"), Decimal("100"), "working-lineage",
                metadata={"research_lineage": {"strategy_id": "breakout-v1"}, "access_token": "do-not-store"},
            )
        )
        broker.apply_partial_fill(opened.order_id, Decimal("1"), fill_id="fill-a")
        restored = PersistentPaperBroker(
            Decimal("1000"), database_path=self.root / "working-lineage.sqlite"
        )
        self.assertEqual(
            restored._orders[opened.order_id].metadata["research_lineage"]["strategy_id"],
            "breakout-v1",
        )
        self.assertNotIn("access_token", restored._orders[opened.order_id].metadata)
        self.assertEqual(
            restored.get_working_orders()[0].metadata["research_lineage"]["strategy_id"],
            "breakout-v1",
        )


if __name__ == "__main__":
    unittest.main()
