from __future__ import annotations

import unittest
from decimal import Decimal

from scripts.paper_report import summarize


class PaperReportTests(unittest.TestCase):
    def test_metrics_include_realized_events_and_drawdown(self):
        rows = [
            {"ts": "2026-11-10T10:00:00+00:00", "status": "filled",
             "realized_pnl": "0", "equity": "1000", "balance": "1000", "open_positions": 1},
            {"ts": "2026-11-11T10:00:00+00:00", "status": "filled",
             "realized_pnl": "25", "equity": "1025", "balance": "1025", "open_positions": 0},
            {"ts": "2026-11-12T10:00:00+00:00", "status": "filled",
             "realized_pnl": "15", "equity": "1015", "balance": "1015", "open_positions": 0},
        ]
        result = summarize(rows)
        self.assertEqual(result["distinct_session_days"], 3)
        self.assertEqual(result["realized_trade_events"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["losses"], 1)
        self.assertEqual(Decimal(result["total_realized_pnl"]), Decimal("15"))
        self.assertEqual(Decimal(result["max_equity_drawdown"]), Decimal(10) / Decimal(1025))

    def test_rejects_empty_ledger(self):
        with self.assertRaises(ValueError):
            summarize([])


if __name__ == "__main__":
    unittest.main()
