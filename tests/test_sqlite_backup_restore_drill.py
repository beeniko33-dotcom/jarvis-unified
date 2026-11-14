"""Backup/restore drill tests for the persistent paper ledger."""
import tempfile
import unittest
from pathlib import Path

from brokers.paper.persistent import PersistentPaperBroker
from scripts.sqlite_backup_restore_drill import backup_restore_drill


class SqliteBackupRestoreDrillTests(unittest.TestCase):
    def test_online_backup_restore_preserves_integrity_counts_and_event_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.sqlite3"
            backup = root / "backup.sqlite3"
            restored = root / "restored.sqlite3"
            PersistentPaperBroker(database_path=source)
            report = backup_restore_drill(source, backup, restored)
            self.assertTrue(report["ok"])
            self.assertEqual(report["integrity"], {
                "source": "ok", "backup": "ok", "restored": "ok"
            })
            self.assertEqual(report["paper_event_chain"]["event_count"], 1)
            self.assertEqual(report["table_record_counts"], {
                "paper_events": 1, "paper_state": 1
            })
            self.assertTrue(backup.is_file())
            self.assertTrue(restored.is_file())

    def test_refuses_to_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.sqlite3"
            backup = root / "backup.sqlite3"
            restored = root / "restored.sqlite3"
            PersistentPaperBroker(database_path=source)
            backup.write_bytes(b"preserve me")
            with self.assertRaises(FileExistsError):
                backup_restore_drill(source, backup, restored)
            self.assertEqual(backup.read_bytes(), b"preserve me")

    def test_requires_three_distinct_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.sqlite3"
            PersistentPaperBroker(database_path=source)
            with self.assertRaises(ValueError):
                backup_restore_drill(source, source, Path(tmp) / "restored.sqlite3")


if __name__ == "__main__":
    unittest.main()
