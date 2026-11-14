import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits
from research.execution_observations import ExecutionObservationJournal
from research.paper_ledger_importer import import_paper_ledger
from research.paper_outcomes import PaperOutcomeError, build_paper_outcome_report


class PaperOutcomeAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "paper.sqlite"
        self.journal = ExecutionObservationJournal(self.root / "learning.sqlite")
        self.clock = lambda: datetime(2026, 11, 14, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_includes_loss_fees_close_and_drawdown(self):
        broker = PersistentPaperBroker(
            Decimal("1000"), database_path=self.source,
            commission_per_side=Decimal("0.1"), clock=self.clock,
        )
        risk = RiskEngine(RiskLimits(
            Decimal("5"), Decimal("50"), 3, False,
        ))
        service = ExecutionService(broker, risk, observation_journal=self.journal)
        order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "entry-1")
        service.submit(order)
        broker.set_last_price("EURUSD", Decimal("8"))
        service.close_position("EURUSD", Decimal("8"))
        import_paper_ledger(self.source, self.journal)

        report = build_paper_outcome_report(self.journal)
        self.assertEqual(report.approved_decisions, 1)
        self.assertEqual(report.rejected_decisions, 0)
        self.assertEqual(report.order_count, 2)
        self.assertEqual(report.filled_orders, 2)
        self.assertEqual(report.close_events, 1)
        self.assertLess(Decimal(report.gross_realized_pnl), Decimal("0"))
        self.assertGreater(Decimal(report.commission_paid), Decimal("0"))
        self.assertLess(Decimal(report.net_realized_after_commission),
                        Decimal(report.gross_realized_pnl))
        self.assertIsNotNone(report.max_observed_drawdown_pct)
        self.assertEqual(len(report.by_utc_day), 1)
        self.assertIn("not individual entry orders", report.limitations[0])

    def test_report_counts_rejections_even_when_no_trade_occurred(self):
        broker = PersistentPaperBroker(Decimal("1000"), database_path=self.source, clock=self.clock)
        risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, True))
        service = ExecutionService(broker, risk, observation_journal=self.journal)
        order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "blocked-1")
        with self.assertRaises(PermissionError):
            service.submit(order)

        report = build_paper_outcome_report(self.journal)
        self.assertEqual(report.rejected_decisions, 1)
        self.assertEqual(report.imported_ledger_events, 0)
        self.assertEqual(report.gross_realized_pnl, "0")
        self.assertEqual(report.commission_paid, "0")
        self.assertEqual(report.order_count, 0)

    def test_partial_fill_and_fill_identity_are_retained(self):
        broker = PersistentPaperBroker(Decimal("1000"), database_path=self.source, clock=self.clock)
        working = broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "working-1")
        )
        broker.apply_partial_fill(
            working.order_id, Decimal("0.4"), Decimal("10"), fill_id="fill-001"
        )
        import_paper_ledger(self.source, self.journal)
        report = build_paper_outcome_report(self.journal)
        self.assertEqual(report.partial_orders, 1)
        self.assertEqual(report.unique_fill_ids, 1)
        self.assertEqual(report.open_working_orders, 1)

    def test_tampered_learning_journal_fails_closed(self):
        broker = PersistentPaperBroker(Decimal("1000"), database_path=self.source, clock=self.clock)
        broker.place_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "entry-1")
        )
        import_paper_ledger(self.source, self.journal)
        with sqlite3.connect(self.journal.path) as db:
            db.execute(
                "UPDATE execution_observations SET payload=? WHERE seq=1",
                ('{"tampered":true}',),
            )
        with self.assertRaises(PaperOutcomeError):
            build_paper_outcome_report(self.journal)

    def test_event_pagination_returns_only_events_after_cursor(self):
        for index in range(3):
            self.journal.append(
                event_id=f"test-{index}", event_type="note",
                data={"index": index}, occurred_at=self.clock(),
            )
        first = self.journal.list_events(limit=2)
        second = self.journal.list_events(limit=2, after_seq=first[-1]["seq"])
        self.assertEqual(len(first), 2)
        self.assertEqual([item["data"]["index"] for item in second], [2])


if __name__ == "__main__":
    unittest.main()
