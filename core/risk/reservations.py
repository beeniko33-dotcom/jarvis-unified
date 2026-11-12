"""Cross-process correlated exposure reservations (paper-only).

Temporary reservations cover the gap between risk check and broker fill.
Committed exposure records durable filled notional so completed orders cannot
disappear from shared capacity accounting after the temporary reservation is released.
Pending transfers record fill→commit failures so a restarted process can recover.
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
    """Atomic temporary reservations, durable committed exposure, pending transfers."""

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
                """CREATE TABLE IF NOT EXISTS exposure_releases (
                    release_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS exposure_pending_releases (
                    release_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS exposure_pending (
                    reservation_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE,
                    client_order_id TEXT,
                    symbol TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    corr_group TEXT,
                    error TEXT,
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
                    if reservation_id:
                        db.execute(
                            "DELETE FROM exposure_reservations WHERE reservation_id=?",
                            (reservation_id,),
                        )
                        db.execute(
                            "DELETE FROM exposure_pending WHERE reservation_id=?",
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
                    db.execute(
                        "DELETE FROM exposure_pending WHERE reservation_id=?",
                        (reservation_id,),
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def record_pending_transfer(
        self,
        *,
        reservation_id: str,
        order_id: str,
        client_order_id: str | None,
        symbol: str,
        notional: Decimal,
        corr_group: str | None,
        error: str,
    ) -> None:
        """Persist a fill that still needs reservation→committed conversion."""
        if not reservation_id.strip() or not order_id.strip():
            raise ReservationError("reservation_id and order_id are required")
        symbol = symbol.strip().upper()
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO exposure_pending"
                    "(reservation_id,order_id,client_order_id,symbol,notional,corr_group,error,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(reservation_id) DO UPDATE SET"
                    " error=excluded.error, created_at=excluded.created_at",
                    (
                        reservation_id,
                        order_id,
                        client_order_id,
                        symbol,
                        str(notional),
                        corr_group,
                        error,
                        now,
                    ),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def list_pending_transfers(self) -> list[dict]:
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute(
                    "SELECT reservation_id,order_id,client_order_id,symbol,notional,"
                    "corr_group,error,created_at FROM exposure_pending ORDER BY created_at"
                ).fetchall()
                db.commit()
            except Exception:
                db.rollback()
                raise
        return [
            {
                "reservation_id": r[0],
                "order_id": r[1],
                "client_order_id": r[2],
                "symbol": r[3],
                "notional": r[4],
                "corr_group": r[5],
                "error": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def reduce_committed_for_symbol(
        self, release_id: str, symbol: str, notional: Decimal
    ) -> None:
        """Idempotently reduce committed exposure after a confirmed position close."""
        if not release_id.strip():
            raise ReservationError("release_id is required")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ReservationError("symbol is required")
        if not notional.is_finite() or notional <= 0:
            raise ReservationError("release notional must be finite and positive")
        now = time.time()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute(
                    "SELECT 1 FROM exposure_releases WHERE release_id=?", (release_id,)
                ).fetchone():
                    db.commit()
                    return
                rows = db.execute(
                    "SELECT commit_id,notional FROM exposure_committed "
                    "WHERE symbol=? ORDER BY created_at,commit_id", (symbol,)
                ).fetchall()
                remaining = notional
                for commit_id, raw in rows:
                    if remaining <= 0:
                        break
                    available = Decimal(raw)
                    consumed = min(available, remaining)
                    left = available - consumed
                    if left == 0:
                        db.execute(
                            "DELETE FROM exposure_committed WHERE commit_id=?", (commit_id,)
                        )
                    else:
                        db.execute(
                            "UPDATE exposure_committed SET notional=? WHERE commit_id=?",
                            (str(left), commit_id),
                        )
                    remaining -= consumed
                if remaining > 0:
                    raise ReservationError(
                        f"cannot release {notional} {symbol}; committed exposure is insufficient"
                    )
                db.execute(
                    "INSERT INTO exposure_releases(release_id,symbol,notional,created_at) "
                    "VALUES(?,?,?,?)", (release_id, symbol, str(notional), now)
                )
                db.execute(
                    "DELETE FROM exposure_pending_releases WHERE release_id=?", (release_id,)
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def record_pending_release(
        self, release_id: str, symbol: str, notional: Decimal, error: str
    ) -> None:
        """Persist a post-close exposure reduction that needs retrying."""
        if not release_id.strip() or not symbol.strip():
            raise ReservationError("release_id and symbol are required")
        if not notional.is_finite() or notional <= 0:
            raise ReservationError("release notional must be finite and positive")
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO exposure_pending_releases"
                    "(release_id,symbol,notional,error,created_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(release_id) DO UPDATE SET error=excluded.error",
                    (release_id, symbol.strip().upper(), str(notional), error, time.time()),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def list_pending_releases(self) -> list[dict]:
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(
                "SELECT release_id,symbol,notional,error,created_at "
                "FROM exposure_pending_releases ORDER BY created_at"
            ).fetchall()
        return [
            {"release_id": row[0], "symbol": row[1], "notional": row[2],
             "error": row[3], "created_at": row[4]}
            for row in rows
        ]

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
                db.execute(
                    "DELETE FROM exposure_pending WHERE reservation_id=?",
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
