"""Tests for the continuous collector session supervisor."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import collector_supervisor as cs
from research.collector_supervisor import (
    FileLock,
    SessionRecord,
    health_snapshot,
    run_continuous,
    run_one_session,
)


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

    def test_stale_lock_is_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "stale.lock"
            # Write a lock owned by a PID that cannot be alive.
            lock_path.write_text("999999999\n", encoding="utf-8")
            lock = FileLock(lock_path, timeout_seconds=1.0)
            self.assertTrue(lock.acquire())
            lock.release()
            self.assertFalse(lock_path.exists())

    def test_live_pid_lock_is_not_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "live.lock"
            lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
            lock = FileLock(lock_path, timeout_seconds=0.4)
            # Current process is alive — acquire must fail within timeout.
            self.assertFalse(lock.acquire())
            # Clean up manually so the test dir can be removed.
            lock_path.unlink(missing_ok=True)


class SupervisorTests(unittest.TestCase):
    def test_successful_session_records_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db = tmp_path / "data.sqlite3"
            lock = tmp_path / "data.sqlite3.lock"
            log_dir = tmp_path / "logs"

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

    def test_continuous_stops_after_max_consecutive_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            results = run_continuous(
                command=["python", "-c", "import sys; sys.exit(1)"],
                db_path=tmp_path / "data.sqlite3",
                lock_path=tmp_path / "data.sqlite3.lock",
                duration_seconds=10,
                log_dir=tmp_path / "logs",
                max_sessions=20,
                pause_between_seconds=0.01,
                max_consecutive_failures=3,
                backoff_base_seconds=0.01,
                backoff_cap_seconds=0.05,
            )
            self.assertEqual(len(results), 3)
            self.assertTrue(all(r.status == "failed" for r in results))

    def test_health_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_dir = tmp_path / "logs"
            db = tmp_path / "data.sqlite3"
            lock = tmp_path / "data.sqlite3.lock"
            # Create one completed session so last_session is populated.
            run_one_session(
                command=["python", "-c", "print('ok')"],
                db_path=db,
                lock_path=lock,
                duration_seconds=10,
                log_dir=log_dir,
            )
            snap = health_snapshot(log_dir=log_dir, db_path=db, lock_path=lock)
            self.assertEqual(snap["session_record_count"], 1)
            self.assertIsInstance(snap["last_session"], dict)
            self.assertEqual(snap["last_session"]["status"], "completed")
            self.assertFalse(snap["lock_held"])
            self.assertIn("note", snap)

    def test_shutdown_flag_stops_continuous(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Force shutdown after first session via the module flag.
            original = cs._SHUTDOWN_REQUESTED
            try:
                cs._SHUTDOWN_REQUESTED = False

                def _flip_after(*args, **kwargs):
                    record = run_one_session(*args, **kwargs)
                    cs._SHUTDOWN_REQUESTED = True
                    return record

                with patch.object(cs, "run_one_session", side_effect=_flip_after):
                    results = run_continuous(
                        command=["python", "-c", "print('ok')"],
                        db_path=tmp_path / "data.sqlite3",
                        lock_path=tmp_path / "data.sqlite3.lock",
                        duration_seconds=10,
                        log_dir=tmp_path / "logs",
                        max_sessions=10,
                        pause_between_seconds=0.01,
                    )
                self.assertEqual(len(results), 1)
            finally:
                cs._SHUTDOWN_REQUESTED = original


if __name__ == "__main__":
    unittest.main()
