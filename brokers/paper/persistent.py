"""Restart-safe, SQLite-backed paper broker wrapper.

SQLite serializes each mutation with BEGIN IMMEDIATE. The complete broker state is
snapshotted into a SHA-256 chained append-only event table in the same transaction.
This remains a simulation only; it is not a broker adapter.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import uuid4
from typing import Callable

from core.models import AccountSnapshot, OrderRequest, OrderResult, Position, Side
from .broker import PaperBroker


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class PersistentPaperBroker(PaperBroker):
    """PaperBroker with transactional persistence, restart recovery and audit verification."""

    def __init__(
        self,
        starting_balance: Decimal = Decimal("10000"),
        *,
        database_path: str | Path,
        commission_per_side: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._persistent_lock = RLock()
        super().__init__(
            starting_balance,
            commission_per_side=commission_per_side,
            slippage_bps=slippage_bps,
        )
        self._peak_equity = Decimal(starting_balance)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS paper_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS paper_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                event_type TEXT NOT NULL, utc_day TEXT NOT NULL, payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE)""")
            row = db.execute("SELECT payload FROM paper_state WHERE singleton=1").fetchone()
            if row is None:
                self._save_snapshot(db)
                initial = self._snapshot()
                self._append_event(db, "initialized", initial, Decimal("0"), Decimal("0"))
            else:
                stored_state = json.loads(row[0])
                self._restore(stored_state)
                self._verify_chain(db)
                latest = db.execute(
                    "SELECT payload FROM paper_events ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                if latest is None or json.loads(latest[0]).get("state") != stored_state:
                    raise RuntimeError(
                        "paper ledger snapshot does not match its audit tail; broker is locked"
                    )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _snapshot(self) -> dict:
        return {
            "balance": str(self._balance),
            "peak_equity": str(self._peak_equity),
            "realized_pnl": str(self._realized_pnl),
            "commission_paid": str(self._commission_paid),
            "positions": [{
                "symbol": p.symbol, "quantity": str(p.quantity),
                "average_price": str(p.average_price), "opened_at": p.opened_at.isoformat()
            } for p in self._positions.values()],
            "orders": [{
                "order_id": o.order_id, "client_order_id": o.client_order_id,
                "symbol": o.symbol, "side": o.side.value, "quantity": str(o.quantity),
                "fill_price": str(o.fill_price), "status": o.status,
                "created_at": o.created_at.isoformat()
            } for o in self._orders.values()],
            "requests": {
                cid: [symbol, side.value, str(qty), str(price)]
                for cid, (symbol, side, qty, price) in self._client_requests.items()
            },
            "last_prices": {k: str(v) for k, v in self._last_prices.items()},
            "commission_per_side": str(self._commission_per_side),
            "slippage_bps": str(self._slippage_bps),
        }

    def _restore(self, state: dict) -> None:
        self._balance = Decimal(state["balance"])
        self._peak_equity = Decimal(state.get("peak_equity", state["balance"]))
        self._realized_pnl = Decimal(state["realized_pnl"])
        self._commission_paid = Decimal(state["commission_paid"])
        self._positions = {
            p["symbol"]: Position(p["symbol"], Decimal(p["quantity"]),
                Decimal(p["average_price"]), _dt(p["opened_at"]))
            for p in state["positions"]
        }
        self._orders = {}
        self._client_ids = {}
        for o in state["orders"]:
            result = OrderResult(o["order_id"], o["client_order_id"], o["symbol"],
                Side(o["side"]), Decimal(o["quantity"]), Decimal(o["fill_price"]),
                o["status"], _dt(o["created_at"]))
            self._orders[result.order_id] = result
            self._client_ids[result.client_order_id] = result
        self._client_requests = {
            cid: (v[0], Side(v[1]), Decimal(v[2]), Decimal(v[3]))
            for cid, v in state["requests"].items()
        }
        self._last_prices = {k: Decimal(v) for k, v in state["last_prices"].items()}
        self._commission_per_side = Decimal(state["commission_per_side"])
        self._slippage_bps = Decimal(state["slippage_bps"])

    def _save_snapshot(self, db: sqlite3.Connection) -> None:
        payload = json.dumps(self._snapshot(), sort_keys=True, separators=(",", ":"))
        db.execute(
            "INSERT INTO paper_state(singleton,payload) VALUES(1,?) "
            "ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload", (payload,)
        )

    def _append_event(
        self, db: sqlite3.Connection, event_type: str, state: dict,
        realized_delta: Decimal, commission_delta: Decimal,
    ) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("persistent broker clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        previous = db.execute(
            "SELECT event_hash FROM paper_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev_hash = previous[0] if previous else "GENESIS"
        event = {
            "state": state, "realized_delta": str(realized_delta),
            "commission_delta": str(commission_delta),
        }
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((prev_hash + "|" + payload).encode()).hexdigest()
        db.execute(
            "INSERT INTO paper_events(created_at,event_type,utc_day,payload,previous_hash,event_hash) "
            "VALUES(?,?,?,?,?,?)",
            (now.isoformat(), event_type, now.date().isoformat(), payload, prev_hash, digest),
        )

    def _verify_chain(self, db: sqlite3.Connection) -> bool:
        previous = "GENESIS"
        for prev_hash, digest, payload in db.execute(
            "SELECT previous_hash,event_hash,payload FROM paper_events ORDER BY seq"
        ):
            expected = hashlib.sha256((previous + "|" + payload).encode()).hexdigest()
            if prev_hash != previous or digest != expected:
                raise RuntimeError("paper ledger integrity failure; broker is locked")
            previous = digest
        return True

    def _refresh_from_db(self, db: sqlite3.Connection) -> None:
        row = db.execute("SELECT payload FROM paper_state WHERE singleton=1").fetchone()
        if row is None:
            raise RuntimeError("paper ledger state is missing; broker is locked")
        self._verify_chain(db)
        try:
            stored_state = json.loads(row[0])
            latest = db.execute(
                "SELECT payload FROM paper_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if latest is None or json.loads(latest[0]).get("state") != stored_state:
                raise RuntimeError(
                    "paper ledger snapshot does not match its audit tail; broker is locked"
                )
            self._restore(stored_state)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("paper ledger snapshot is malformed; broker is locked") from exc

    def _mutate(self, event_type: str, operation: Callable[[], object]):
        with self._persistent_lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._refresh_from_db(db)
                before_realized = self._realized_pnl
                before_commission = self._commission_paid
                result = operation()
                current_equity = super(PersistentPaperBroker, self).get_account().equity
                self._peak_equity = max(self._peak_equity, current_equity)
                state = self._snapshot()
                self._save_snapshot(db)
                self._append_event(
                    db, event_type, state,
                    self._realized_pnl - before_realized,
                    self._commission_paid - before_commission,
                )
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def place_order(self, order: OrderRequest) -> OrderResult:
        return self._mutate("paper_order", lambda: super(PersistentPaperBroker, self).place_order(order))

    def set_last_price(self, symbol: str, price: Decimal | float | str) -> None:
        self._mutate("mark_price", lambda: super(PersistentPaperBroker, self).set_last_price(symbol, price))

    def close_position(self, symbol: str, price: Decimal | float) -> OrderResult:
        close_price = Decimal(str(price))
        normalized = symbol.strip().upper()
        if not close_price.is_finite() or close_price <= 0:
            raise ValueError("close price must be finite and positive")

        def close_atomically():
            position = self._positions.get(normalized)
            if position is None:
                raise ValueError(f"no open position for {normalized}")
            side = Side.SELL if position.quantity > 0 else Side.BUY
            request = OrderRequest(
                normalized, side, abs(position.quantity), close_price, f"close-{uuid4()}"
            )
            return super(PersistentPaperBroker, self).place_order(request)

        return self._mutate("paper_close", close_atomically)

    def get_account(self) -> AccountSnapshot:
        with self._persistent_lock, self._connect() as db:
            self._refresh_from_db(db)
            base = super().get_account()
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("persistent broker clock must be timezone-aware")
            day = now.astimezone(timezone.utc).date().isoformat()
            daily_realized = Decimal("0")
            daily_commission = Decimal("0")
            for (payload,) in db.execute(
                "SELECT payload FROM paper_events WHERE utc_day=?", (day,)
            ):
                event = json.loads(payload)
                daily_realized += Decimal(event["realized_delta"])
                daily_commission += Decimal(event["commission_delta"])
            return AccountSnapshot(
                balance=base.balance, equity=base.equity, realized_pnl=base.realized_pnl,
                open_positions=base.open_positions, commission_paid=base.commission_paid,
                daily_realized_pnl=daily_realized, daily_commission_paid=daily_commission,
                daily_accounting_available=True,
                peak_equity=self._peak_equity,
                drawdown_pct=(
                    max(Decimal("0"), (self._peak_equity - base.equity) / self._peak_equity * Decimal("100"))
                    if self._peak_equity > 0 else Decimal("0")
                ),
            )

    def get_positions(self) -> list[Position]:
        with self._persistent_lock, self._connect() as db:
            self._refresh_from_db(db)
            return super().get_positions()

    def verify_ledger(self) -> bool:
        with self._persistent_lock, self._connect() as db:
            return self._verify_chain(db)

    def ledger_event_count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM paper_events").fetchone()[0])
