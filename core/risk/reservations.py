"""Cross-process correlated exposure reservations (paper-only).

Reservations are held in SQLite so concurrent paper processes share the same
notional budget before an order is submitted. They do not enable live trading.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from threading import RLock


class ReservationError(ValueError):
    """Raised when a reservation cannot be created or does not exist."""


class ExposureReservationStore:
    """Atomic notional reservations keyed by reservation_id."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                """CREATE TABLE IF NOT EXISTS exposure_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    corr_group TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_res_symbol ON exposure_reservations(symbol)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_res_group ON exposure_reservations(corr_group)"
            )
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _purge_expired(self, db: sqlite3.Connection, now: float) -> None:
        db.execute(
            "DELETE FROM exposure_reservations WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )

    def reserve(
        self,
        reservation_id: str,
        symbol: str,
        notional: Decimal,
        *,
        corr_group: str | None = None,
        ttl_seconds: float | None = 120.0,
    ) -> None:
        if not reservation_id.strip():
            raise ReservationError("reservation_id is required")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ReservationError("symbol is required")
        if not notional.is_finite() or notional <= 0:
            raise ReservationError("notional must be finite and positive")
        now = time.time()
        expires = None if ttl_seconds is None else now + float(ttl_seconds)
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._purge_expired(db, now)
                existing = db.execute(
                    "SELECT 1 FROM exposure_reservations WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if existing:
                    raise ReservationError(f"reservation already exists: {reservation_id}")
                db.execute(
                    "INSERT INTO exposure_reservations"
                    "(reservation_id,symbol,notional,corr_group,created_at,expires_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (
                        reservation_id,
                        symbol,
                        str(notional),
                        corr_group,
                        now,
                        expires,
                    ),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def release(self, reservation_id: str) -> None:
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                cur = db.execute(
                    "DELETE FROM exposure_reservations WHERE reservation_id=?",
                    (reservation_id,),
                )
                db.commit()
                if cur.rowcount == 0:
                    raise ReservationError(f"unknown reservation: {reservation_id}")
            except Exception:
                db.rollback()
                raise

    def reserved_for_symbol(self, symbol: str) -> Decimal:
        symbol = symbol.strip().upper()
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            self._purge_expired(db, now)
            db.commit()
            rows = db.execute(
                "SELECT notional FROM exposure_reservations WHERE symbol=?",
                (symbol,),
            ).fetchall()
        total = Decimal("0")
        for (raw,) in rows:
            total += Decimal(raw)
        return total

    def reserved_for_group(self, corr_group: str) -> Decimal:
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            self._purge_expired(db, now)
            db.commit()
            rows = db.execute(
                "SELECT notional FROM exposure_reservations WHERE corr_group=?",
                (corr_group,),
            ).fetchall()
        total = Decimal("0")
        for (raw,) in rows:
            total += Decimal(raw)
        return total

    def count(self) -> int:
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            self._purge_expired(db, now)
            db.commit()
            return int(db.execute("SELECT COUNT(*) FROM exposure_reservations").fetchone()[0])
