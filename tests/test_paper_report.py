from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path

from scripts.paper_report import load_rows, main, summarize


class PaperReportTests(unittest.TestCase):
    def test_metrics_include_realized_events_and_drawdown(self):
        rows = [
            {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 1},
            {"ts": "2026-11-11T10:00:00+00:00", "status": "filled",
             "realized_pnl": "25", "commission_paid": "1", "equity": "1025", "balance": "1025", "open_positions": 0},
            {"ts": "2026-11-12T10:00:00+00:00", "status": "filled",
             "realized_pnl": "15", "commission_paid": "2", "equity": "1015", "balance": "1015", "open_positions": 0},
        ]
        result = summarize(rows)
        self.assertEqual(result["distinct_session_days"], 3)
        self.assertEqual(result["consecutive_session_days"], 3)
        self.assertEqual(result["days_without_ledger_events"], 0)
        self.assertEqual(result["realized_trade_events"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["losses"], 1)
        self.assertEqual(Decimal(result["total_realized_pnl_before_commission"]), Decimal("15"))
        self.assertEqual(Decimal(result["total_commission_paid"]), Decimal("2"))
        self.assertEqual(Decimal(result["net_realized_pnl_after_commission"]), Decimal("13"))
        self.assertEqual(Decimal(result["max_equity_drawdown"]), Decimal(10) / Decimal(1025))

    def test_rejects_empty_ledger(self):
        with self.assertRaises(ValueError):
            summarize([])

    def test_utc_dates_are_used_for_offsets(self):
        rows = [
            {"ts": "2026-11-11T23:30:00-02:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 0},
            {"ts": "2026-11-12T02:30:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 0},
        ]

        result = summarize(rows)

        self.assertEqual(result["session_days"], ["2026-11-12"])
        self.assertEqual(result["distinct_session_days"], 1)

    def test_gaps_break_consecutive_day_coverage(self):
        rows = [
            {"ts": f"2026-11-{day:02d}T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 0}
            for day in (10, 11, 13, 14, 15)
        ]

        result = summarize(rows)

        self.assertEqual(result["distinct_session_days"], 5)
        self.assertEqual(result["calendar_span_days"], 6)
        self.assertEqual(result["days_without_ledger_events"], 1)
        self.assertEqual(result["consecutive_session_days"], 3)

    def test_min_days_gate_rejects_enough_distinct_days_with_a_gap(self):
        rows = [
            {"ts": f"2026-11-{day:02d}T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000",
             "balance": "1000", "open_positions": 0}
            for day in (10, 11, 13, 14, 15)
        ]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ledger.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                result = main([str(path), "--min-days", "5"])

        self.assertEqual(result, 2)
        self.assertIn("longest run is 3 days", output.getvalue())

    def test_rejects_naive_timestamp(self):
        row = {"ts": "2026-11-10T10:00:00", "status": "filled",
               "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 0}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ledger.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                load_rows(path)

    def test_rejects_incomplete_slippage_fields(self):
        row = {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
               "realized_pnl": "0", "commission_paid": "0", "equity": "1000",
               "balance": "1000", "open_positions": 0, "raw_price": "10"}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ledger.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                load_rows(path)

    def test_rejects_out_of_order_rows_instead_of_sorting(self):
        rows = [
            {"ts": "2026-11-11T10:00:00+00:00", "status": "filled",
             "realized_pnl": "5", "commission_paid": "0", "equity": "1005", "balance": "1005", "open_positions": 0},
            {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000", "open_positions": 0},
        ]
        with self.assertRaisesRegex(ValueError, "out of order"):
            summarize(rows)

    def test_slippage_is_side_aware_and_weighted_by_notional(self):
        rows = [
            {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000",
             "open_positions": 1, "raw_price": "100", "fill_price": "101",
             "side": "buy", "quantity": "2"},
            {"ts": "2026-11-11T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000", "balance": "1000",
             "open_positions": 0, "raw_price": "100", "fill_price": "99",
             "side": "sell", "quantity": "2"},
        ]

        result = summarize(rows)

        self.assertEqual(result["slippage_observations"], 2)
        self.assertEqual(Decimal(result["net_slippage_cost"]), Decimal("4"))
        self.assertEqual(Decimal(result["notional_weighted_slippage_bps"]), Decimal("100"))

    def test_report_does_not_infer_rejection_rate_from_fills(self):
        rows = [
            {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "commission_paid": "0", "equity": "1000",
             "balance": "1000", "open_positions": 0},
        ]

        result = summarize(rows)

        self.assertIsNone(result["rejected_entry_rate"])
        self.assertEqual(result["attribution_coverage"], "0")


if __name__ == "__main__":
    unittest.main()
