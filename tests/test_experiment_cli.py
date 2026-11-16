import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from main import main
from research.experience_store import ExperienceStore


class ExperimentCliTests(unittest.TestCase):
    def test_list_verify_compare_and_source_verification_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "experience.sqlite3"
            ledger = root / "ledger.db"
            journal = root / "journal.db"
            ledger.write_bytes(b"ledger")
            journal.write_bytes(b"journal")
            import hashlib

            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(days=10)
            store = ExperienceStore(db)
            common = dict(
                hypothesis="CLI experiment test", strategy_version="sma-v1",
                dataset_id="dataset-1", dataset_hash="a" * 64,
                data_status="verified", start_at=start.isoformat(),
                end_at=end.isoformat(),
                source_ledger_hash=hashlib.sha256(ledger.read_bytes()).hexdigest(),
                source_journal_hash=hashlib.sha256(journal.read_bytes()).hexdigest(),
            )
            left = store.record(
                name="left", config={"window": 10}, metrics={"net_pnl": 1}, **common
            )
            right = store.record(
                name="right", config={"window": 20}, metrics={"net_pnl": 2}, **common
            )

            def run(*args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    main([*args, "--experience-db", str(db)])
                return output.getvalue()

            listing = run("--experiment-list")
            self.assertIn(left.experiment_id, listing)
            verified = run("--experiment-verify", left.experiment_id)
            self.assertIn('"integrity_verified": true', verified)
            source_result = run(
                "--experiment-verify-sources", left.experiment_id,
                str(ledger), str(journal),
            )
            self.assertIn('"status": "integrity_matched_unverified"', source_result)
            run(
                "--experiment-verify-sources", right.experiment_id,
                str(ledger), str(journal),
            )
            comparison = run("--experiment-compare", left.experiment_id, right.experiment_id)
            self.assertIn('"comparable": false', comparison)
            self.assertIn('source_references_not_independently_verified', comparison)
            self.assertNotIn('"net_pnl": "1"', comparison)


if __name__ == "__main__":
    unittest.main()
