"""Append-only SQLite ledger for Deriv Options intent and contract lifecycle."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

_ALLOWED_EVENT_FIELDS = {
    "proposal_id", "contract_id", "transaction_id", "underlying_symbol",
    "contract_type", "currency", "amount", "basis", "duration",
    "duration_unit", "ask_price", "payout", "buy_price", "status",
    "profit", "is_sold", "is_expired", "sold_for", "reason",
}


class DerivContractLedger:
    """Durable event journal. It intentionally never accepts arbitrary metadata."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS deriv_contract_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    client_intent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    contract_id TEXT,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS deriv_events_intent_idx
                ON deriv_contract_events(client_intent_id, sequence)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS deriv_events_contract_idx
                ON deriv_contract_events(contract_id, sequence)
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS deriv_buy_claims (
                    client_intent_id TEXT PRIMARY KEY,
                    claimed_at TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("ledger payload must be a dictionary")
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            if key not in _ALLOWED_EVENT_FIELDS:
                continue
            if isinstance(value, (str, int, bool)) or value is None:
                safe[key] = value
            elif isinstance(value, float):
                raise ValueError("floating-point ledger values are not accepted")
            else:
                safe[key] = str(value)
        return safe

    def append(
        self, client_intent_id: str, event_type: str, payload: dict[str, Any],
        *, contract_id: str | None = None,
    ) -> dict[str, Any]:
        if not client_intent_id or not event_type:
            raise ValueError("intent identity and event type are required")
        safe = self._safe_payload(payload)
        event = {
            "event_id": str(uuid4()),
            "client_intent_id": client_intent_id,
            "event_type": event_type,
            "contract_id": contract_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": safe,
        }
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO deriv_contract_events
                (event_id, client_intent_id, event_type, contract_id, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (event["event_id"], client_intent_id, event_type, contract_id,
                 event["occurred_at"], encoded),
            )
        return event

    def events(self, client_intent_id: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT event_id, client_intent_id, event_type, contract_id,
                   occurred_at, payload_json FROM deriv_contract_events"""
        args: tuple[Any, ...] = ()
        if client_intent_id is not None:
            query += " WHERE client_intent_id = ?"
            args = (client_intent_id,)
        query += " ORDER BY sequence"
        with self._lock, self._connect() as db:
            rows = db.execute(query, args).fetchall()
        return [{
            "event_id": row[0], "client_intent_id": row[1], "event_type": row[2],
            "contract_id": row[3], "occurred_at": row[4], "payload": json.loads(row[5]),
        } for row in rows]

    def claim_buy(self, client_intent_id: str) -> None:
        """Atomically make a client intent single-use across processes/restarts."""
        if not client_intent_id:
            raise ValueError("client intent identity is required")
        try:
            with self._lock, self._connect() as db:
                db.execute(
                    "INSERT INTO deriv_buy_claims(client_intent_id, claimed_at) VALUES (?, ?)",
                    (client_intent_id, datetime.now(timezone.utc).isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise PermissionError("buy already claimed; reconcile before any retry") from exc

    def has_intent(self, client_intent_id: str) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM deriv_contract_events WHERE client_intent_id = ? LIMIT 1",
                (client_intent_id,),
            ).fetchone()
        return row is not None

    def open_stake_total(self) -> str:
        """Conservative exposure: pending, ambiguous and open buys remain reserved."""
        states: dict[str, str] = {}
        for event in self.events():
            if event["event_type"] in {"buy_requested", "buy_unknown", "contract_bought"}:
                amount = event["payload"].get("amount")
                if amount is None:
                    history = self.events(event["client_intent_id"])
                    amount = next(
                        (item["payload"].get("amount") for item in history
                         if item["event_type"] == "buy_requested"), None
                    )
                if amount is not None:
                    states[event["client_intent_id"]] = str(amount)
            elif event["event_type"] in {"contract_sold", "contract_settled"}:
                states.pop(event["client_intent_id"], None)
        from decimal import Decimal
        return str(sum((Decimal(amount) for amount in states.values()), Decimal("0")))
