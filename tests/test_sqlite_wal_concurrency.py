"""Concurrent first-time opens must not fail with "database is locked".

``PRAGMA journal_mode=WAL`` ignores busy_timeout, so stores that issue it directly
fail intermittently when several instances open one new database at once.
"""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from brokers.paper.persistent import PersistentPaperBroker
from core.sqlite_wal import enable_wal
from research.paper_replay import PaperReplay

THREADS = 4
ROUNDS = 20


def _open_concurrently(factory) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for round_no in range(ROUNDS):
            database = Path(tmp) / f"round-{round_no}.db"
            barrier = threading.Barrier(THREADS, timeout=30)

            def work() -> None:
                try:
                    barrier.wait()
                    factory(database)
                except Exception as exc:  # noqa: BLE001 - collect every failure
                    errors.append(f"{type(exc).__name__}: {exc}")

            threads = [threading.Thread(target=work) for _ in range(THREADS)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
    return errors


class SqliteWalConcurrencyTests(unittest.TestCase):
    def test_paper_replay_concurrent_open(self):
        errors = _open_concurrently(lambda database: PaperReplay(database).close())
        self.assertEqual(errors, [])

    def test_persistent_paper_broker_concurrent_open(self):
        errors = _open_concurrently(lambda database: PersistentPaperBroker(database_path=database))
        self.assertEqual(errors, [])

    def test_enable_wal_reraises_non_lock_errors(self):
        class Broken:
            def execute(self, _sql):
                raise sqlite3.OperationalError("disk I/O error")

        with self.assertRaises(sqlite3.OperationalError):
            enable_wal(Broken())

    def test_enable_wal_gives_up_after_deadline(self):
        class AlwaysLocked:
            def execute(self, _sql):
                raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            enable_wal(AlwaysLocked(), timeout=0.05)


if __name__ == "__main__":
    unittest.main()
