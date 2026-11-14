import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.experience_store import ExperienceStore, chronological_split


class ExperienceStoreTests(unittest.TestCase):
    def test_records_immutable_experiment_with_dataset_and_config_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "experience.sqlite3")
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            item = store.record(
                name="baseline", hypothesis="SMA baseline comparison",
                strategy_version="sma-v1", config={"window": 20},
                dataset_id="fixture-1", dataset_hash="sha256:abc",
                data_status="historical", start_at=start.isoformat(),
                end_at=(start + timedelta(days=10)).isoformat(),
                metrics={"trades": 12, "net_return": -0.02, "max_drawdown": 0.05},
            )
            self.assertEqual(len(item.config_hash), 64)
            self.assertEqual(len(item.metrics_hash), 64)
            self.assertTrue(store.verify(item.experiment_id))
            self.assertEqual(store.list()[0], item)

    def test_synthetic_and_historical_statuses_remain_segregated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "experience.sqlite3")
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for status in ("historical", "synthetic"):
                store.record(
                    name=status, hypothesis="test", strategy_version="v1",
                    config={}, dataset_id=status, dataset_hash="hash",
                    data_status=status, start_at=start.isoformat(),
                    end_at=(start + timedelta(days=1)).isoformat(), metrics={},
                )
            self.assertEqual(len(store.list(data_status="historical")), 1)
            self.assertEqual(len(store.list(data_status="synthetic")), 1)

    def test_chronological_split_has_no_overlap_or_future_leakage(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [(start + timedelta(days=i)).isoformat() for i in range(10)]
        split = chronological_split(timestamps)
        self.assertEqual(split, {
            "train": [0, 1, 2, 3, 4, 5],
            "validation": [6, 7],
            "test": [8, 9],
        })
        self.assertLess(timestamps[split["train"][-1]], timestamps[split["validation"][0]])
        self.assertLess(timestamps[split["validation"][-1]], timestamps[split["test"][0]])

    def test_rejects_unsorted_timestamps_and_nan_metrics(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            chronological_split([(start + timedelta(days=1)).isoformat(), start.isoformat()])
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "experience.sqlite3")
            with self.assertRaises(ValueError):
                store.record(
                    name="bad", hypothesis="bad", strategy_version="v1", config={},
                    dataset_id="d", dataset_hash="h", data_status="synthetic",
                    start_at=start.isoformat(), end_at=(start + timedelta(days=1)).isoformat(),
                    metrics={"return": float("nan")},
                )


if __name__ == "__main__":
    unittest.main()
