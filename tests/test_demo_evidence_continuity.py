import unittest

from research.demo_evidence_continuity import (
    DailyDemoHeartbeat,
    DemoContinuityError,
    assess_demo_continuity,
)


class DemoEvidenceContinuityTests(unittest.TestCase):
    def hb(self, day, event_id=None):
        return DailyDemoHeartbeat(day, event_id or f"heartbeat:{day}")

    def test_counts_streak_ending_on_as_of_day(self):
        report = assess_demo_continuity(
            [self.hb("2026-11-14"), self.hb("2026-11-15"), self.hb("2026-11-16")],
            as_of_utc_day="2026-11-16",
        )
        self.assertEqual(report.consecutive_utc_days, 3)
        self.assertEqual(report.observed_days, 3)
        self.assertFalse(report.evidence_eligible)
        self.assertEqual(report.provider_authenticity_verified, 0)

    def test_gap_resets_streak_instead_of_bridging(self):
        report = assess_demo_continuity(
            [self.hb("2026-11-13"), self.hb("2026-11-15"), self.hb("2026-11-16")],
            as_of_utc_day="2026-11-16",
        )
        self.assertEqual(report.consecutive_utc_days, 2)

    def test_missing_as_of_day_means_zero_current_streak(self):
        report = assess_demo_continuity(
            [self.hb("2026-11-14"), self.hb("2026-11-15")],
            as_of_utc_day="2026-11-16",
        )
        self.assertEqual(report.consecutive_utc_days, 0)
        self.assertEqual(report.missing_days_in_streak, 1)

    def test_duplicate_day_rejected(self):
        with self.assertRaises(DemoContinuityError):
            assess_demo_continuity(
                [self.hb("2026-11-16", "a"), self.hb("2026-11-16", "b")],
                as_of_utc_day="2026-11-16",
            )

    def test_duplicate_event_id_rejected(self):
        with self.assertRaises(DemoContinuityError):
            assess_demo_continuity(
                [self.hb("2026-11-15", "same"), self.hb("2026-11-16", "same")],
                as_of_utc_day="2026-11-16",
            )

    def test_future_day_rejected(self):
        with self.assertRaises(DemoContinuityError):
            assess_demo_continuity([self.hb("2026-11-17")], as_of_utc_day="2026-11-16")

    def test_noncanonical_date_rejected(self):
        with self.assertRaises(DemoContinuityError):
            DailyDemoHeartbeat("2026-1-2", "heartbeat")

    def test_empty_history_is_zero_not_30_days(self):
        report = assess_demo_continuity([], as_of_utc_day="2026-11-16")
        self.assertEqual(report.consecutive_utc_days, 0)
        self.assertEqual(report.latest_heartbeat_utc_day, None)


if __name__ == "__main__":
    unittest.main()
