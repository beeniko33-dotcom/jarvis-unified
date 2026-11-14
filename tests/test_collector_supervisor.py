"""Tests for the continuous collector session supervisor."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
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

    def test_lock_left_by_crashed_process_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "crashed.lock"
            child_code = (
                "import sys,time; from pathlib import Path; "
                "from research.collector_supervisor import FileLock; "
                "lock=FileLock(Path(sys.argv[1])); "
                "assert lock.acquire(); print('LOCKED', flush=True); time.sleep(60)"
            )
            child = subprocess.Popen(
                [sys.executable, "-c", child_code, str(lock_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "LOCKED")
                self.assertTrue(lock_path.exists())
                child.kill()
                child.wait(timeout=5)
                recovered = FileLock(lock_path, timeout_seconds=1.0)
                self.assertTrue(recovered.acquire())
                recovered.release()
                self.assertFalse(lock_path.exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.stdout.close()
                child.stderr.close()

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

    def test_successful_session_rotation_records_each_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = run_continuous(
                command=["python", "-c", "print('session')"],
                db_path=root / "data.sqlite3",
                lock_path=root / "data.sqlite3.lock",
                duration_seconds=10,
                log_dir=root / "logs",
                max_sessions=2,
                pause_between_seconds=0,
            )
            self.assertEqual([item.status for item in results], ["completed", "completed"])
            records = list((root / "logs").glob("session-*.json"))
            self.assertEqual(len(records), 2)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group signal integration test")
    def test_sigterm_interrupts_child_and_records_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_pid_file = root / "child.pid"
            wrapper = (
                "import sys,time; "
                "from pathlib import Path; "
                "from research import collector_supervisor as cs; "
                "cs._install_signal_handlers(); "
                "cs.run_one_session(command=[sys.executable,'-c',"
                + repr("import os,time; from pathlib import Path; Path(" + repr(str(child_pid_file)) + ").write_text(str(os.getpid())); time.sleep(60)")
                + "], db_path=Path(sys.argv[1])/'db.sqlite3', "
                "lock_path=Path(sys.argv[1])/'db.lock', duration_seconds=120, "
                "log_dir=Path(sys.argv[1])/'logs', shutdown_grace_seconds=1)"
            )
            parent = subprocess.Popen(
                [sys.executable, "-c", wrapper, str(root)],
                cwd=str(Path.cwd()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 8
                while not child_pid_file.exists() and time.monotonic() < deadline:
                    if parent.poll() is not None:
                        self.fail("supervisor exited before child process started")
                    time.sleep(0.05)
                self.assertTrue(child_pid_file.exists(), "child process did not start")
                child_pid = int(child_pid_file.read_text())
                os.kill(parent.pid, __import__("signal").SIGTERM)
                parent.wait(timeout=8)
                session_records = list((root / "logs").glob("session-*.json"))
                self.assertEqual(len(session_records), 1)
                record = json.loads(session_records[0].read_text())
                self.assertEqual(record["status"], "shutdown")
                self.assertIsNotNone(record["ended_at"])
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=3)

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
