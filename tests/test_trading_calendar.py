import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from research.trading_calendar import TradingCalendar


CONFIG = {
    "version": "test-six-hour-v1",
    "timezone": "UTC",
    "weekdays": [0, 1, 2, 3, 4],
    "session_start_utc_hour": 7,
    "session_end_utc_hour": 13,
    "minimum_covered_hours": 6,
    "closures": [],
}


class TradingCalendarTests(unittest.TestCase):
    def calendar(self, config=None):
        return TradingCalendar(json.dumps(config or CONFIG).encode())

    def stamps(self, day):
        return [datetime(day.year, day.month, day.day, hour, 15, tzinfo=timezone.utc).isoformat()
                for hour in range(7, 13)]

    def test_six_hour_window_requires_all_six_buckets(self):
        cal = self.calendar()
        day = date(2026, 11, 16)
        self.assertTrue(cal.daily_coverage(self.stamps(day), day)["complete"])
        self.assertFalse(cal.daily_coverage(self.stamps(day)[:-1], day)["complete"])

    def test_weekends_are_neutral(self):
        cal = self.calendar()
        self.assertFalse(cal.is_expected_trading_day(date(2026, 11, 15)))
        self.assertEqual(cal.expected_hours(date(2026, 11, 15)), ())

    def test_only_explicit_closures_are_neutral(self):
        config = dict(CONFIG, closures=["2026-11-16"])
        cal = self.calendar(config)
        self.assertFalse(cal.is_expected_trading_day(date(2026, 11, 16)))
        self.assertTrue(cal.is_expected_trading_day(date(2026, 11, 17)))

    def test_missing_hour_breaks_streak(self):
        cal = self.calendar()
        monday = date(2026, 11, 16)
        tuesday = date(2026, 11, 17)
        stamps = self.stamps(monday) + self.stamps(tuesday)[:-1]
        streak, _ = cal.consecutive_covered_days(
            stamps, datetime(2026, 11, 18, 14, tzinfo=timezone.utc)
        )
        self.assertEqual(streak, 0)

    def test_calendar_rejects_partial_daily_threshold(self):
        config = dict(CONFIG, minimum_covered_hours=5)
        with self.assertRaisesRegex(ValueError, "all configured session hours"):
            self.calendar(config)

    def test_calendar_hash_changes_when_rules_change(self):
        first = self.calendar()
        changed = dict(CONFIG, version="test-six-hour-v2")
        second = self.calendar(changed)
        self.assertNotEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
