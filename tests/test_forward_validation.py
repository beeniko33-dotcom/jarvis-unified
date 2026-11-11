import json
import tempfile
import unittest
from pathlib import Path
from research.forward_validation import ForwardEvidenceStore, validate_observation


class ForwardValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ForwardEvidenceStore(Path(self.tmp.name) / "forward.sqlite3",
            instrument="EURUSD", provider="ExampleFeed", interval="1h",
            strategy_id="sma-crossover-long", strategy_version="1.0.0")
        self.addCleanup(self.store.close)

    def item(self, day, time="12:00:00Z"):
        return {"observed_at": f"{day}T{time}", "instrument": "EURUSD",
            "provider": "ExampleFeed", "source": "provider-stream-v1",
            "interval": "1h", "strategy_id": "sma-crossover-long",
            "strategy_version": "1.0.0", "price": "1.08500"}

    def test_offset_is_normalized_to_utc_day(self):
        item = validate_observation(self.item("2026-01-02", "01:00:00+02:00"))
        self.assertEqual(item["utc_day"], "2026-01-01")
        self.assertTrue(item["observed_at"].endswith("+00:00"))

    def test_naive_timestamp_and_wrong_provenance_rejected(self):
        bad = self.item("2026-01-01")
        bad["observed_at"] = "2026-01-01T12:00:00"
        with self.assertRaises(ValueError):
            self.store.ingest(bad)
        bad = self.item("2026-01-01")
        bad["provider"] = "unverified"
        with self.assertRaises(ValueError):
            self.store.ingest(bad)

    def test_thirty_consecutive_days_pass_coverage_gate_but_not_certification(self):
        from datetime import date, timedelta
        start = date(2026, 1, 1)
        for offset in range(30):
            day = (start + timedelta(days=offset)).isoformat()
            self.assertTrue(self.store.ingest(self.item(day)))
        report = self.store.report(30)
        self.assertEqual(report["latest_consecutive_utc_day_streak"], 30)
        self.assertEqual(report["level_3_forward_evidence_gate"], "PASS")
        self.assertFalse(report["level_3_certification"])
        self.assertTrue(report["event_chain_valid"])

    def test_missing_day_breaks_streak_and_duplicate_is_idempotent(self):
        self.store.ingest(self.item("2026-01-01"))
        self.assertFalse(self.store.ingest(self.item("2026-01-01")))
        self.store.ingest(self.item("2026-01-03"))
        report = self.store.report(2)
        self.assertEqual(report["latest_consecutive_utc_day_streak"], 1)
        self.assertEqual(report["level_3_forward_evidence_gate"], "NOT_MET")
        self.assertEqual(report["observation_count"], 2)

    def test_restart_preserves_audit_chain(self):
        self.store.ingest(self.item("2026-01-01"))
        self.store.close()
        self.store = ForwardEvidenceStore(Path(self.tmp.name) / "forward.sqlite3",
            instrument="EURUSD", provider="ExampleFeed", interval="1h",
            strategy_id="sma-crossover-long", strategy_version="1.0.0")
        self.assertTrue(self.store.verify_chain())


if __name__ == "__main__":
    unittest.main()
