from datetime import datetime, timedelta, timezone
import unittest

from research.source_health import SourceEvent, assess_source_health


class SourceHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    def event(self, seconds_ago, **flags):
        return SourceEvent("feed-a", self.now - timedelta(seconds=seconds_ago), **flags)

    def assess(self, events, **overrides):
        options = {"expected_interval_seconds": 60, "outage_after_seconds": 180, "now": self.now}
        options.update(overrides)
        return assess_source_health("feed-a", events, **options)

    def test_regular_cadence_is_reported_without_evidence_credit(self):
        report = self.assess([self.event(120), self.event(60), self.event(0)])
        self.assertEqual(report.status, "CADENCE_OBSERVED")
        self.assertEqual(report.missing_intervals, 0)
        self.assertFalse(report.evidence_eligible)
        self.assertEqual(report.provenance, "candidate_unverified")

    def test_missing_intervals_are_counted(self):
        report = self.assess([self.event(180), self.event(0)])
        self.assertEqual(report.missing_intervals, 2)
        self.assertEqual(report.status, "GAPS_DETECTED")

    def test_outage_is_reported_when_last_event_is_too_old(self):
        report = self.assess([self.event(240)])
        self.assertTrue(report.outage)
        self.assertEqual(report.status, "OUTAGE_SUSPECTED")

    def test_empty_source_is_no_data_and_outage_suspected(self):
        report = self.assess([])
        self.assertEqual(report.status, "NO_DATA")
        self.assertTrue(report.outage)
        self.assertIsNone(report.last_event_at)

    def test_duplicate_timestamps_do_not_create_false_intervals(self):
        report = self.assess([self.event(60), self.event(60), self.event(0)])
        self.assertEqual(report.missing_intervals, 0)

    def test_quality_flags_are_counted(self):
        report = self.assess([self.event(60, duplicate=True, stale=True),
                              self.event(0, out_of_order=True, clock_skew=True)])
        self.assertEqual(report.duplicate_observations, 1)
        self.assertEqual(report.stale_observations, 1)
        self.assertEqual(report.out_of_order_observations, 1)
        self.assertEqual(report.clock_skew_observations, 1)

    def test_events_from_other_sources_are_ignored(self):
        report = self.assess([self.event(0),
                              SourceEvent("feed-b", self.now - timedelta(seconds=500))])
        self.assertEqual(report.observations, 1)
        self.assertEqual(report.status, "CADENCE_OBSERVED")

    def test_naive_now_is_rejected(self):
        with self.assertRaises(ValueError):
            self.assess([self.event(0)], now=datetime(2026, 11, 15, 12, 0))

    def test_invalid_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            self.assess([self.event(0)], expected_interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
