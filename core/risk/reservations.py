"""Cross-process correlated exposure reservations (paper-only).

Temporary reservations cover the gap between risk check and broker fill.
Committed exposure records durable filled notional so completed orders cannot
disappear from shared capacity accounting after the temporary reservation is released.
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
    """Atomic temporary reservations plus durable committed exposure."""

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
                """CREATE TABLE IF NOT EXISTS exposure_committed (
                    commit_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    corr_group TEXT,
                    created_at REAL NOT NULL
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_res_symbol ON exposure_reservations(symbol)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_res_group ON exposure_reservations(corr_group)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_com_symbol ON exposure_committed(symbol)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_com_group ON exposure_committed(corr_group)"
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

    def _sum_reserved(
        self, db: sqlite3.Connection, *,
        symbol: str | None = None,
        corr_group: str | None = None,
    ) -> Decimal:
        if symbol is not None:
            rows = db.execute(
                "SELECT notional FROM exposure_reservations WHERE symbol=?",
                (symbol,),
            ).fetchall()
        elif corr_group is not None:
            rows = db.execute(
                "SELECT notional FROM exposure_reservations WHERE corr_group=?",
                (corr_group,),
            ).fetchall()
        else:
            rows = []
        return sum((Decimal(raw) for (raw,) in rows), Decimal("0"))

    def _sum_committed(
        self, db: sqlite3.Connection, *,
        symbol: str | None = None,
        corr_group: str | None = None,
    ) -> Decimal:
        if symbol is not None:
            rows = db.execute(
                "SELECT notional FROM exposure_committed WHERE symbol=?",
                (symbol,),
            ).fetchall()
        elif corr_group is not None:
            rows = db.execute(
                "SELECT notional FROM exposure_committed WHERE corr_group=?",
                (corr_group,),
            ).fetchall()
        else:
            rows = []
        return sum((Decimal(raw) for (raw,) in rows), Decimal("0"))

    def reserve(
        self,
        reservation_id: str,
        symbol: str,
        notional: Decimal,
        *,
        corr_group: str | None = None,
        ttl_seconds: float | None = 120.0,
        max_symbol_notional: Decimal | None = None,
        max_group_notional: Decimal | None = None,
        existing_symbol_exposure: Decimal = Decimal("0"),
        existing_group_exposure: Decimal = Decimal("0"),
    ) -> None:
        """Insert a temporary reservation if capacity remains.

        Capacity uses: caller-reported position exposure + reserved + committed.
        Check and insert share one BEGIN IMMEDIATE transaction.
        """
        if not reservation_id.strip():
            raise ReservationError("reservation_id is required")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ReservationError("symbol is required")
        if not notional.is_finite() or notional <= 0:
            raise ReservationError("notional must be finite and positive")
        for value, label in (
            (existing_symbol_exposure, "existing_symbol_exposure"),
            (existing_group_exposure, "existing_group_exposure"),
        ):
            if not value.is_finite() or value < 0:
                raise ReservationError(f"{label} must be finite and non-negative")
        if max_symbol_notional is not None and (
            not max_symbol_notional.is_finite() or max_symbol_notional <= 0
        ):
            raise ReservationError("max_symbol_notional must be finite and positive")
        if max_group_notional is not None and (
            not max_group_notional.is_finite() or max_group_notional <= 0
        ):
            raise ReservationError("max_group_notional must be finite and positive")

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

                reserved_symbol = self._sum_reserved(db, symbol=symbol)
                committed_symbol = self._sum_committed(db, symbol=symbol)
                if max_symbol_notional is not None:
                    total = (
                        existing_symbol_exposure
                        + reserved_symbol
                        + committed_symbol
                        + notional
                    )
                    if total > max_symbol_notional:
                        raise ReservationError("per-symbol exposure limit exceeded")

                if max_group_notional is not None and corr_group is not None:
                    reserved_group = self._sum_reserved(db, corr_group=corr_group)
                    committed_group = self._sum_committed(db, corr_group=corr_group)
                    total_g = (
                        existing_group_exposure
                        + reserved_group
                        + committed_group
                        + notional
                    )
                    if total_g > max_group_notional:
                        raise ReservationError("correlated exposure limit exceeded")

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

    def commit_exposure(
        self,
        commit_id: str,
        symbol: str,
        notional: Decimal,
        *,
        corr_group: str | None = None,
        reservation_id: str | None = None,
    ) -> None:
        """Record durable filled notional and optionally drop the temporary reservation.

        Atomic: insert committed row and delete reservation in one transaction so
        exposure never disappears between fill and release.
        """
        if not commit_id.strip():
            raise ReservationError("commit_id is required")
        symbol = symbol.strip().upper()
        if not notional.is_finite() or notional <= 0:
            raise ReservationError("notional must be finite and positive")
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                exists = db.execute(
                    "SELECT 1 FROM exposure_committed WHERE commit_id=?",
                    (commit_id,),
                ).fetchone()
                if exists:
                    # Idempotent commit for the same fill/order key.
                    if reservation_id:
                        db.execute(
                            "DELETE FROM exposure_reservations WHERE reservation_id=?",
                            (reservation_id,),
                        )
                    db.commit()
                    return
                db.execute(
                    "INSERT INTO exposure_committed"
                    "(commit_id,symbol,notional,corr_group,created_at) VALUES(?,?,?,?,?)",
                    (commit_id, symbol, str(notional), corr_group, now),
                )
                if reservation_id:
                    db.execute(
                        "DELETE FROM exposure_reservations WHERE reservation_id=?",
                        (reservation_id,),
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def release_committed(self, commit_id: str) -> None:
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                cur = db.execute(
                    "DELETE FROM exposure_committed WHERE commit_id=?", (commit_id,)
                )
                db.commit()
                if cur.rowcount == 0:
                    raise ReservationError(f"unknown commit: {commit_id}")
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
            db.execute("BEGIN IMMEDIATE")
            try:
                self._purge_expired(db, now)
                total = self._sum_reserved(db, symbol=symbol)
                db.commit()
                return total
            except Exception:
                db.rollback()
                raise

    def committed_for_symbol(self, symbol: str) -> Decimal:
        symbol = symbol.strip().upper()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                total = self._sum_committed(db, symbol=symbol)
                db.commit()
                return total
            except Exception:
                db.rollback()
                raise

    def reserved_for_group(self, corr_group: str) -> Decimal:
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._purge_expired(db, now)
                total = self._sum_reserved(db, corr_group=corr_group)
                db.commit()
                return total
            except Exception:
                db.rollback()
                raise

    def committed_for_group(self, corr_group: str) -> Decimal:
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                total = self._sum_committed(db, corr_group=corr_group)
                db.commit()
                return total
            except Exception:
                db.rollback()
                raise

    def count(self) -> int:
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._purge_expired(db, now)
                n = int(db.execute("SELECT COUNT(*) FROM exposure_reservations").fetchone()[0])
                db.commit()
                return n
            except Exception:
                db.rollback()
                raise
