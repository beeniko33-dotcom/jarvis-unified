from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PaperBroker
from core.models import OrderRequest, Side
from scripts import paper_daily_check

D0 = date(2026, 11, 10)


def _rows(tmp: Path, day_offsets: list[int]) -> list[dict]:
    """One continuous broker account; each fill pair is stamped onto the given UTC day offsets."""
    broker = PaperBroker(
        Decimal("10000"),
        commission_per_side=Decimal("0.1"),
        slippage_bps=Decimal("5"),
        ledger_path=tmp / "ledger.jsonl",
    )
    for n, _offset in enumerate(day_offsets):
        symbol = f"SYM{n}"
        broker.place_order(OrderRequest(symbol, Side.BUY, Decimal("1"), Decimal("1.10"), f"b-{n}"))
        broker.close_position(symbol, Decimal("1.12"))
    rows = broker.ledger_entries()
    for index, row in enumerate(rows):
        offset = day_offsets[index // 2]
        stamp = datetime(D0.year, D0.month, D0.day, 12, tzinfo=timezone.utc) + timedelta(days=offset)
        row["ts"] = stamp.isoformat()
    return rows


class DailyCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_healthy_when_every_day_through_today_has_a_session(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 1, 2]), as_of=D0 + timedelta(days=2))
        self.assertTrue(result["healthy"], result["alerts"])
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["current_streak_days"], 3)
        self.assertEqual(result["missing_days"], [])

    def test_missing_today_is_flagged_but_streak_is_alive(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 1]), as_of=D0 + timedelta(days=2))
        self.assertEqual(result["state"], "missing_today")
        self.assertFalse(result["healthy"])
        self.assertEqual(result["current_streak_days"], 2)

    def test_gap_in_the_middle_is_reported_and_resets_the_streak(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 1, 3]), as_of=D0 + timedelta(days=3))
        self.assertFalse(result["healthy"])
        self.assertEqual(result["missing_days"], [(D0 + timedelta(days=2)).isoformat()])
        self.assertEqual(result["current_streak_days"], 1)

    def test_streak_broken_after_two_missed_days(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 1]), as_of=D0 + timedelta(days=4))
        self.assertEqual(result["state"], "streak_broken")
        self.assertFalse(result["healthy"])

    def test_future_dated_events_are_flagged(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 5]), as_of=D0 + timedelta(days=1))
        self.assertEqual(result["state"], "future_dated")
        self.assertFalse(result["healthy"])

    def test_tampered_ledger_makes_the_check_unhealthy(self):
        rows = _rows(self.tmp, [0, 1])
        rows[2]["balance"] = "1"
        result = paper_daily_check.check(rows, as_of=D0 + timedelta(days=1))
        self.assertFalse(result["healthy"])
        self.assertEqual(result["reconciliation_status"], "discrepancies")

    def test_failed_journal_verification_is_an_alert(self):
        result = paper_daily_check.check(
            _rows(self.tmp, [0]), as_of=D0, journal_ok=False
        )
        self.assertFalse(result["healthy"])
        self.assertTrue(any("hash-chain" in alert for alert in result["alerts"]))

    def test_streak_never_claims_level_3_credit(self):
        result = paper_daily_check.check(_rows(self.tmp, [0, 1, 2]), as_of=D0 + timedelta(days=2))
        self.assertFalse(result["streak_counts_toward_level_3"])

    def test_cli_exit_codes_and_as_of(self):
        rows = _rows(self.tmp, [0, 1])
        path = self.tmp / "dated.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                paper_daily_check.main([str(path), "--as-of", (D0 + timedelta(days=1)).isoformat()]), 0
            )
            self.assertEqual(
                paper_daily_check.main([str(path), "--as-of", (D0 + timedelta(days=3)).isoformat()]), 2
            )


if __name__ == "__main__":
    unittest.main()
