import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.forward_validation import ForwardEvidenceStore, validate_observation


class ForwardValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = datetime(2026, 1, 30, 12, tzinfo=timezone.utc)
        self.clock = lambda: self.now
        self.store = self.make_store()
        self.addCleanup(self.store.close)

    def make_store(self, verifier=None):
        return ForwardEvidenceStore(
            Path(self.tmp.name) / "forward.sqlite3",
            instrument="EURUSD", provider="ExampleFeed", interval="1h",
            strategy_id="sma-crossover-long", strategy_version="1.0.0",
            provenance_verifier=verifier, clock=self.clock,
            max_observation_age=timedelta(minutes=10),
        )

    def item(self, when=None, source="provider-stream-v1"):
        when = when or self.now
        return {
            "observed_at": when.isoformat(), "instrument": "EURUSD",
            "provider": "ExampleFeed", "source": source, "interval": "1h",
            "strategy_id": "sma-crossover-long", "strategy_version": "1.0.0",
            "price": "1.08500",
        }

    def test_offset_is_normalized_to_utc_day(self):
        item = validate_observation({
            **self.item(), "observed_at": "2026-01-30T14:00:00+02:00"
        })
        self.assertEqual(item["utc_day"], "2026-01-30")
        self.assertTrue(item["observed_at"].endswith("+00:00"))

    def test_naive_and_malformed_timestamps_rejected(self):
        bad = self.item()
        bad["observed_at"] = "2026-01-30T12:00:00"
        with self.assertRaises(ValueError):
            self.store.ingest(bad)
        bad["observed_at"] = None
        with self.assertRaises(ValueError):
            self.store.ingest(bad)

    def test_stale_backfilled_and_future_observations_rejected(self):
        stale = self.item(self.now - timedelta(days=30))
        with self.assertRaisesRegex(ValueError, "stale/backfilled"):
            self.store.ingest(stale)
        future = self.item(self.now + timedelta(minutes=2))
        with self.assertRaisesRegex(ValueError, "future"):
            self.store.ingest(future)

    def test_unverified_candidates_never_count_toward_streak(self):
        for offset in range(5):
            when = self.now - timedelta(minutes=offset)
            self.store.ingest(self.item(when))
        report = self.store.report(1)
        self.assertEqual(report["unverified_candidate_count"], 5)
        self.assertEqual(report["verified_observation_count"], 0)
        self.assertEqual(report["latest_consecutive_verified_utc_day_streak"], 0)
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
        self.assertFalse(report["level_3_certification"])

    def test_only_verifier_approved_records_count(self):
        self.store.close()
        self.store = self.make_store(verifier=lambda item: item["source"] == "provider-signed-v1")
        self.store.ingest(self.item(self.now, "provider-signed-v1"))
        self.store.ingest(self.item(self.now - timedelta(minutes=1)))
        report = self.store.report(1)
        self.assertEqual(report["verified_observation_count"], 1)
        self.assertEqual(report["unverified_candidate_count"], 1)
        self.assertEqual(report["level_3_forward_evidence_gate"], "PASS")
        self.assertFalse(report["level_3_certification"])

    def test_missing_day_breaks_verified_streak(self):
        self.store.close()
        self.store = self.make_store(verifier=lambda item: True)
        self.now = datetime(2026, 1, 28, 12, tzinfo=timezone.utc)
        self.store.ingest(self.item())
        self.now = datetime(2026, 1, 30, 12, tzinfo=timezone.utc)
        self.store.ingest(self.item())
        report = self.store.report(2)
        self.assertEqual(report["latest_consecutive_verified_utc_day_streak"], 1)
        self.assertEqual(report["level_3_forward_evidence_gate"], "NOT_MET")

    def test_report_fails_closed_when_latest_verified_observation_goes_stale(self):
        self.store.close()
        self.store = self.make_store(verifier=lambda item: True)
        self.store.ingest(self.item())
        self.assertEqual(self.store.report(1)["level_3_forward_evidence_gate"], "PASS")
        self.now += timedelta(minutes=11)
        report = self.store.report(1)
        self.assertFalse(report["latest_verified_observation_fresh"])
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_STALE")
        self.assertFalse(report["level_3_certification"])

    def test_concurrent_store_instances_preserve_one_hash_chain(self):
        from concurrent.futures import ThreadPoolExecutor
        database = Path(self.tmp.name) / "concurrent.sqlite3"
        barrier = __import__("threading").Barrier(2)

        def append(offset):
            store = ForwardEvidenceStore(
                database, instrument="EURUSD", provider="ExampleFeed", interval="1h",
                strategy_id="sma-crossover-long", strategy_version="1.0.0",
                provenance_verifier=lambda item: True, clock=self.clock,
            )
            try:
                barrier.wait()
                return store.ingest(self.item(self.now - timedelta(seconds=offset)))
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(append, (0, 1)))
        check = ForwardEvidenceStore(
            database, instrument="EURUSD", provider="ExampleFeed", interval="1h",
            strategy_id="sma-crossover-long", strategy_version="1.0.0",
            provenance_verifier=lambda item: True, clock=self.clock,
        )
        try:
            self.assertEqual(results, [True, True])
            self.assertTrue(check.verify_chain())
            self.assertEqual(check.report(1)["verified_observation_count"], 2)
        finally:
            check.close()

    def test_duplicate_is_idempotent(self):
        self.assertTrue(self.store.ingest(self.item()))
        self.assertFalse(self.store.ingest(self.item()))
        self.assertEqual(self.store.report()["observation_count"], 1)

    def test_restart_preserves_audit_chain(self):
        self.store.ingest(self.item())
        self.store.close()
        self.store = self.make_store()
        self.assertTrue(self.store.verify_chain())


if __name__ == "__main__":
    unittest.main()
