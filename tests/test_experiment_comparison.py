import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.experience_store import ExperienceStore
from research.experiment_comparison import compare_experiments


class ExperimentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ExperienceStore(self.root / "experience.sqlite3")
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.end = self.start + timedelta(days=30)
        self.ledger = self.root / "ledger.sqlite"
        self.journal = self.root / "journal.sqlite"
        self.ledger.write_bytes(b"verified-paper-ledger-artifact")
        self.journal.write_bytes(b"verified-observation-journal-artifact")
        self.ledger_hash = hashlib.sha256(self.ledger.read_bytes()).hexdigest()
        self.journal_hash = hashlib.sha256(self.journal.read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, name, config, metrics, **kwargs):
        return self.store.record(
            name=name,
            hypothesis="Compare immutable paper experiment evidence",
            strategy_version="strategy-v1",
            config=config,
            dataset_id="eurusd-paper-window-01",
            dataset_hash="a" * 64,
            data_status="verified",
            start_at=self.start.isoformat(),
            end_at=self.end.isoformat(),
            metrics=metrics,
            source_ledger_hash=kwargs.get("ledger_hash", self.ledger_hash),
            source_journal_hash=kwargs.get("journal_hash", self.journal_hash),
        )

    def test_matching_artifacts_enable_deterministic_comparison(self):
        left = self.record("baseline", {"window": 20}, {"net_pnl": -2.0, "trades": 4})
        right = self.record("candidate", {"window": 30}, {"net_pnl": 1.5, "trades": 5})
        self.assertEqual(self.store.verify_source_artifacts(
            left.experiment_id, ledger_path=self.ledger, journal_path=self.journal
        )["status"], "verified")
        self.assertEqual(self.store.verify_source_artifacts(
            right.experiment_id, ledger_path=self.ledger, journal_path=self.journal
        )["status"], "verified")
        first = compare_experiments(self.store, left.experiment_id, right.experiment_id)
        second = compare_experiments(self.store, left.experiment_id, right.experiment_id)
        self.assertTrue(first.comparable)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.metric_deltas, {"net_pnl": "3.5", "trades": "1"})

    def test_missing_source_hashes_are_incomparable_not_ranked(self):
        left = self.store.record(
            name="left", hypothesis="test", strategy_version="v1", config={},
            dataset_id="d", dataset_hash="b" * 64, data_status="verified",
            start_at=self.start.isoformat(), end_at=self.end.isoformat(), metrics={"pnl": 1},
        )
        right = self.store.record(
            name="right", hypothesis="test", strategy_version="v2", config={},
            dataset_id="d", dataset_hash="b" * 64, data_status="verified",
            start_at=self.start.isoformat(), end_at=self.end.isoformat(), metrics={"pnl": 2},
        )
        report = compare_experiments(self.store, left.experiment_id, right.experiment_id)
        self.assertFalse(report.comparable)
        self.assertIn("source_ledger_hash_missing", report.reasons)
        self.assertEqual(report.metric_deltas, {})

    def test_source_artifact_mismatch_is_persisted_and_blocks_comparison(self):
        left = self.record("left", {}, {"pnl": 1})
        right = self.record("right", {}, {"pnl": 2})
        self.store.verify_source_artifacts(
            left.experiment_id, ledger_path=self.ledger, journal_path=self.journal
        )
        self.journal.write_bytes(b"changed journal")
        result = self.store.verify_source_artifacts(
            right.experiment_id, ledger_path=self.ledger, journal_path=self.journal
        )
        self.assertEqual(result["status"], "mismatch")
        report = compare_experiments(self.store, left.experiment_id, right.experiment_id)
        self.assertFalse(report.comparable)
        self.assertIn("source_journal_hash_mismatch", report.reasons)

    def test_dataset_and_time_mismatch_are_explicit(self):
        left = self.record("left", {}, {"pnl": 1})
        right = self.store.record(
            name="right", hypothesis="test", strategy_version="v2", config={},
            dataset_id="different", dataset_hash="c" * 64, data_status="verified",
            start_at=self.start.isoformat(),
            end_at=(self.end + timedelta(days=1)).isoformat(), metrics={"pnl": 2},
            source_ledger_hash=self.ledger_hash, source_journal_hash=self.journal_hash,
        )
        report = compare_experiments(self.store, left.experiment_id, right.experiment_id)
        self.assertFalse(report.comparable)
        self.assertIn("dataset_identity_or_hash_mismatch", report.reasons)
        self.assertIn("time_window_mismatch", report.reasons)

    def test_source_verification_does_not_persist_local_paths(self):
        item = self.record("private", {}, {"pnl": 0})
        self.store.verify_source_artifacts(
            item.experiment_id, ledger_path=self.ledger, journal_path=self.journal
        )
        db_text = (self.root / "experience.sqlite3").read_bytes()
        self.assertNotIn(str(self.ledger).encode(), db_text)
        self.assertNotIn(str(self.journal).encode(), db_text)


if __name__ == "__main__":
    unittest.main()
