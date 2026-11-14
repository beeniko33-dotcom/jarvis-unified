"""Shared helper for switching a SQLite connection to WAL under contention."""

from __future__ import annotations

import sqlite3
import time


def enable_wal(db: sqlite3.Connection, *, timeout: float = 30.0) -> None:
    """Run ``PRAGMA journal_mode=WAL``, retrying while another connection holds the lock.

    Switching to WAL needs a brief exclusive lock and ignores ``busy_timeout``, so
    concurrent first-time opens of the same database can raise "database is locked".
    Non-lock errors, and lock errors past the deadline, are re-raised unchanged.
    """
    deadline = time.monotonic() + timeout
    delay = 0.01
    while True:
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if ("locked" not in message and "busy" not in message) or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)
