from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from brokers.paper import PaperBroker
from core.models import OrderRequest, Side
from research.ledger_reconciliation import reconcile_ledger
from scripts import paper_reconcile


def _ledger_rows(tmp: Path, *, commission="0.1", slippage="5") -> list[dict]:
    broker = PaperBroker(
        Decimal("10000"),
        commission_per_side=Decimal(commission),
        slippage_bps=Decimal(slippage),
        ledger_path=tmp / "ledger.jsonl",
    )
    broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("2"), Decimal("1.10"), "c-1"))
    broker.place_order(OrderRequest("GBPUSD", Side.SELL, Decimal("3"), Decimal("1.25"), "c-2"))
    broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.12"), "c-3"))
    broker.close_position("EURUSD", Decimal("1.15"))
    broker.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("5"), Decimal("1.20"), "c-4"))  # flips short to long
    broker.close_position("GBPUSD", Decimal("1.22"))
    return broker.ledger_entries()


class LedgerReconciliationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_honest_ledger_with_adds_closes_and_flips_reconciles(self):
        result = reconcile_ledger(_ledger_rows(self.tmp))
        self.assertEqual(result["status"], "reconciled", result)
        self.assertEqual(result["discrepancies"], [])
        self.assertEqual(result["replayed_open_positions"], {})

    def test_zero_cost_ledger_reconciles(self):
        result = reconcile_ledger(_ledger_rows(self.tmp, commission="0", slippage="0"))
        self.assertEqual(result["status"], "reconciled", result)

    def test_edited_realized_pnl_is_caught(self):
        rows = _ledger_rows(self.tmp)
        rows[3]["realized_pnl"] = str(Decimal(rows[3]["realized_pnl"]) + Decimal("1"))
        result = reconcile_ledger(rows)
        self.assertEqual(result["status"], "discrepancies")
        self.assertIn("realized_pnl", {d["field"] for d in result["discrepancies"]})

    def test_edited_balance_is_caught_after_the_first_row(self):
        rows = _ledger_rows(self.tmp)
        rows[2]["balance"] = str(Decimal(rows[2]["balance"]) + Decimal("5"))
        result = reconcile_ledger(rows)
        self.assertEqual(result["status"], "discrepancies")
        self.assertIn(3, {d["row"] for d in result["discrepancies"] if d["field"] == "balance"})

    def test_hidden_fee_change_is_caught(self):
        rows = _ledger_rows(self.tmp)
        rows[1]["commission"] = "0.5"
        result = reconcile_ledger(rows)
        self.assertEqual(result["status"], "discrepancies")

    def test_deleted_row_is_caught(self):
        rows = _ledger_rows(self.tmp)
        del rows[2]
        self.assertEqual(reconcile_ledger(rows)["status"], "discrepancies")

    def test_unexplained_open_position_count_is_caught(self):
        rows = _ledger_rows(self.tmp)
        rows[-1]["open_positions"] = 1
        result = reconcile_ledger(rows)
        self.assertEqual(result["status"], "discrepancies")
        self.assertIn("open_positions", {d["field"] for d in result["discrepancies"]})

    def test_open_position_at_end_is_reported(self):
        broker = PaperBroker(Decimal("1000"), ledger_path=self.tmp / "open.jsonl")
        broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "o-1"))
        result = reconcile_ledger(broker.ledger_entries())
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(result["replayed_open_positions"], {"EURUSD": "1"})

    def test_partial_fills_are_incomplete_never_reconciled(self):
        broker = PaperBroker(Decimal("1000"), ledger_path=self.tmp / "partial.jsonl")
        working = broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("2"), Decimal("1.10"), "p-1")
        )
        broker.apply_partial_fill(working.order_id, Decimal("1"), fill_id="f-1")
        result = reconcile_ledger(broker.ledger_entries())
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["unsupported_rows"])

    def test_input_rows_are_not_mutated(self):
        rows = _ledger_rows(self.tmp)
        before = copy.deepcopy(rows)
        reconcile_ledger(rows)
        self.assertEqual(rows, before)

    def test_appended_independent_sessions_are_flagged_with_a_cause(self):
        first = _ledger_rows(self.tmp)
        second_dir = self.tmp / "second"
        second_dir.mkdir()
        second = _ledger_rows(second_dir)
        result = reconcile_ledger(first + second)
        self.assertEqual(result["status"], "discrepancies")
        self.assertEqual(result["suspected_session_boundaries"], [len(first) + 1])
        self.assertIn("new broker instance", result["boundary_note"])

    def test_clean_ledger_has_no_suspected_boundaries(self):
        result = reconcile_ledger(_ledger_rows(self.tmp))
        self.assertEqual(result["suspected_session_boundaries"], [])
        self.assertIsNone(result["boundary_note"])

    def test_empty_ledger_is_an_error(self):
        with self.assertRaises(ValueError):
            reconcile_ledger([])

    def test_cli_exit_codes(self):
        _ledger_rows(self.tmp)
        path = self.tmp / "ledger.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paper_reconcile.main([str(path)]), 0)
        lines = path.read_text().splitlines()
        row = json.loads(lines[2])
        row["balance"] = "1"
        lines[2] = json.dumps(row)
        path.write_text("\n".join(lines) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paper_reconcile.main([str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
