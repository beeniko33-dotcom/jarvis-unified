"""Tests for the continuous collector session supervisor."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.collector_supervisor import FileLock, run_one_session, SessionRecord


class FileLockTests(unittest.TestCase):
    def test_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "test.lock"
            lock1 = FileLock(lock_path, timeout_seconds=0.5)
            self.assertTrue(lock1.acquire())
            lock2 = FileLock(lock_path, timeout_seconds=0.3)
            self.assertFalse(lock2.acquire())
            lock1.release()
            self.assertTrue(lock2.acquire())
            lock2.release()


class SupervisorTests(unittest.TestCase):
    def test_successful_session_records_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db = tmp_path / "data.sqlite3"
            lock = tmp_path / "data.sqlite3.lock"
            log_dir = tmp_path / "logs"

            # Use a trivial successful command
            record = run_one_session(
                command=["python", "-c", "print('ok')"],
                db_path=db,
                lock_path=lock,
                duration_seconds=30,
                log_dir=log_dir,
            )
            self.assertIsInstance(record, SessionRecord)
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.exit_code, 0)
            self.assertTrue((log_dir / f"session-{record.session_id}.json").exists())

    def test_failed_command_records_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            record = run_one_session(
                command=["python", "-c", "import sys; sys.exit(7)"],
                db_path=tmp_path / "data.sqlite3",
                lock_path=tmp_path / "data.sqlite3.lock",
                duration_seconds=30,
                log_dir=tmp_path / "logs",
            )
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.exit_code, 7)

    def test_lock_contention_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lock_path = tmp_path / "busy.lock"
            # Hold the lock
            holder = FileLock(lock_path, timeout_seconds=0.1)
            self.assertTrue(holder.acquire())
            try:
                record = run_one_session(
                    command=["python", "-c", "print('should not run')"],
                    db_path=tmp_path / "data.sqlite3",
                    lock_path=lock_path,
                    duration_seconds=30,
                    log_dir=tmp_path / "logs",
                )
                self.assertEqual(record.status, "skipped_lock")
            finally:
                holder.release()


if __name__ == "__main__":
    unittest.main()
