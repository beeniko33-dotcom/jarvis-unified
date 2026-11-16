from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from research.evidence_pipeline import (
    MarketObservation, ResearchEvidencePipeline, validate_forecast_window,
)


class ResearchEvidencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline = ResearchEvidencePipeline(Path(self.tmp.name) / "research.sqlite", max_age_seconds=60)
        self.now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def observation(self, seconds_ago=1, *, value=100, source="feed-a"):
        event = self.now - timedelta(seconds=seconds_ago)
        return MarketObservation(source, event, self.now, "EURUSD", "1m", {"mid": value})

    def test_ingest_is_durable_and_never_verified(self):
        result = self.pipeline.ingest(self.observation(), now=self.now)
        self.assertTrue(result.accepted)
        reopened = ResearchEvidencePipeline(Path(self.tmp.name) / "research.sqlite")
        report = reopened.report()
        self.assertEqual(report["observations"], 1)
        self.assertEqual(report["verified_observations"], 0)
        self.assertFalse(report["evidence_eligible"])

    def test_duplicate_content_is_rejected(self):
        observation = self.observation()
        self.assertTrue(self.pipeline.ingest(observation, now=self.now).accepted)
        duplicate = self.pipeline.ingest(observation, now=self.now)
        self.assertTrue(duplicate.duplicate)
        self.assertFalse(duplicate.accepted)

    def test_stale_data_is_flagged_and_not_eligible(self):
        result = self.pipeline.ingest(self.observation(120), now=self.now)
        self.assertTrue(result.stale)
        self.assertFalse(result.evidence_eligible)

    def test_future_clock_skew_is_flagged(self):
        event = self.now + timedelta(seconds=20)
        observation = MarketObservation("feed-a", event, self.now, "EURUSD", "1m", {"mid": 1.0})
        self.assertTrue(self.pipeline.ingest(observation, now=self.now).clock_skew)

    def test_out_of_order_data_is_retained_but_flagged(self):
        self.pipeline.ingest(self.observation(2, value=1), now=self.now)
        earlier = self.observation(10, value=2)
        result = self.pipeline.ingest(earlier, now=self.now)
        self.assertTrue(result.out_of_order)
        self.assertEqual(self.pipeline.report()["out_of_order"], 1)

    def test_source_health_is_scoped(self):
        self.pipeline.ingest(self.observation(source="feed-a"), now=self.now)
        self.pipeline.ingest(self.observation(source="feed-b", value=101), now=self.now)
        self.assertEqual(self.pipeline.report(source_id="feed-a")["observations"], 1)

    def test_timezone_is_required(self):
        with self.assertRaises(ValueError):
            MarketObservation("feed", datetime(2026, 1, 1), self.now, "EURUSD", "1m", {"mid": 1})

    def test_forecast_temporal_leakage_is_rejected(self):
        decision = self.now
        with self.assertRaises(ValueError):
            validate_forecast_window(
                decision_at=decision, outcome_start=decision - timedelta(seconds=1),
                outcome_end=decision + timedelta(seconds=10),
            )

    def test_valid_forecast_window_is_accepted(self):
        validate_forecast_window(
            decision_at=self.now, outcome_start=self.now + timedelta(seconds=1),
            outcome_end=self.now + timedelta(minutes=1),
        )


if __name__ == "__main__":
    unittest.main()
