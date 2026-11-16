"""Attribution and rejected-entry evidence for the JSONL paper ledger."""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits
from research.execution_observations import ExecutionObservationJournal
from scripts import paper_report

LINEAGE = {
    "research_lineage": {
        "strategy_id": "unit_test_strategy",
        "strategy_version": "7",
        "quote_source": "synthetic_fixture",
    }
}


def _service(tmp: Path, *, release: bool = True):
    broker = PaperBroker(Decimal("10000"), ledger_path=tmp / "ledger.jsonl")
    risk = RiskEngine(RiskLimits(Decimal("50"), Decimal("100"), 5, True))
    if release:
        risk.release_kill_switch(explicit_operator_action=True)
    journal = ExecutionObservationJournal(tmp / "obs.sqlite3")
    return broker, ExecutionService(broker, risk, observation_journal=journal), journal


class LedgerLineageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_lineage_is_written_to_the_ledger_row(self):
        broker, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "a-1", dict(LINEAGE)))
        row = broker.ledger_entries()[0]
        self.assertEqual(row["strategy_id"], "unit_test_strategy")
        self.assertEqual(row["strategy_version"], "7")
        self.assertEqual(row["quote_source"], "synthetic_fixture")

    def test_fill_without_lineage_stays_unattributed(self):
        broker, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "a-2"))
        row = broker.ledger_entries()[0]
        for key in ("strategy_id", "strategy_version", "quote_source"):
            self.assertNotIn(key, row)

    def test_secret_like_lineage_values_are_never_persisted(self):
        broker, svc, _ = _service(self.tmp)
        bad = {"research_lineage": {"strategy_id": "ok_id", "quote_source": "api_key=abc123"}}
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "a-3", bad))
        row = broker.ledger_entries()[0]
        self.assertEqual(row["strategy_id"], "ok_id")
        self.assertNotIn("quote_source", row)
        self.assertNotIn("abc123", json.dumps(row))

    def test_core_ledger_fields_cannot_be_overwritten_by_lineage(self):
        broker, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "a-4", dict(LINEAGE)))
        row = broker.ledger_entries()[0]
        self.assertEqual(row["status"], "filled")
        self.assertEqual(row["symbol"], "EURUSD")


class RejectedEntryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rejected_and_approved_entries_are_journaled(self):
        broker, svc, journal = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "r-1", dict(LINEAGE)))
        with self.assertRaises(PermissionError):
            # notional 500 exceeds the 50 per-trade hard limit
            svc.submit(OrderRequest("GBPUSD", Side.BUY, Decimal("400"), Decimal("1.25"), "r-2", dict(LINEAGE)))
        types = [event["event_type"] for event in journal.list_events()]
        self.assertEqual(types.count("risk_approved"), 1)
        self.assertEqual(types.count("risk_rejected"), 1)
        # Rejected entries never reach the broker, so the fill ledger stays fill-only.
        self.assertEqual(len(broker.ledger_entries()), 1)

    def test_kill_switch_rejections_are_journaled(self):
        _, svc, journal = _service(self.tmp, release=False)
        with self.assertRaises(PermissionError):
            svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "k-1", dict(LINEAGE)))
        self.assertEqual([e["event_type"] for e in journal.list_events()], ["risk_rejected"])

    def test_decision_stats_rate(self):
        events = [
            {"event_type": "risk_approved"},
            {"event_type": "risk_approved"},
            {"event_type": "risk_rejected"},
            {"event_type": "reservation_rejected"},
            {"event_type": "broker_submission_error"},
        ]
        stats = paper_report.decision_stats(events)
        self.assertEqual(stats["decided_entries"], 3)
        self.assertEqual(stats["rejected_entries"], 2)
        self.assertEqual(Decimal(stats["rejected_entry_rate"]), Decimal(2) / Decimal(3))
        self.assertEqual(stats["broker_submission_errors"], 1)

    def test_rate_is_none_when_no_decisions(self):
        stats = paper_report.decision_stats([])
        self.assertIsNone(stats["rejected_entry_rate"])

    def test_report_reports_unavailable_without_journal(self):
        broker, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "u-1", dict(LINEAGE)))
        result = paper_report.summarize(paper_report.load_rows(self.tmp / "ledger.jsonl"))
        self.assertIsNone(result["rejected_entry_rate"])
        self.assertIn("--observations-db", result["rejected_entry_rate_note"])

    def test_report_includes_rate_and_attribution_with_journal(self):
        broker, svc, journal = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "w-1", dict(LINEAGE)))
        with self.assertRaises(PermissionError):
            svc.submit(OrderRequest("GBPUSD", Side.BUY, Decimal("400"), Decimal("1.25"), "w-2", dict(LINEAGE)))
        result = paper_report.summarize(
            paper_report.load_rows(self.tmp / "ledger.jsonl"), journal.list_events()
        )
        self.assertEqual(Decimal(result["rejected_entry_rate"]), Decimal("0.5"))
        self.assertEqual(result["attributed_fill_count"], 1)
        self.assertEqual(result["attribution_coverage"], "1")

    def test_cli_refuses_a_tampered_journal(self):
        _, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "t-1", dict(LINEAGE)))
        with closing(sqlite3.connect(self.tmp / "obs.sqlite3")) as conn, conn as db:
            db.execute("UPDATE execution_observations SET payload='{\"tampered\":true}'")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            paper_report.main([
                str(self.tmp / "ledger.jsonl"),
                "--observations-db", str(self.tmp / "obs.sqlite3"),
            ])
        self.assertIn("hash-chain", err.getvalue())

    def test_cli_requires_existing_journal(self):
        _, svc, _ = _service(self.tmp)
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "n-1", dict(LINEAGE)))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            paper_report.main([
                str(self.tmp / "ledger.jsonl"),
                "--observations-db", str(self.tmp / "missing.sqlite3"),
            ])


if __name__ == "__main__":
    unittest.main()
