"""Read-only, idempotent import of verified persistent paper-ledger events.

The source ledger is never modified. All imported facts retain the source ledger
identity, sequence and event hash so downstream learning can trace every claim.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from brokers.paper.broker import _paper_metadata
from research.execution_observations import ExecutionObservationJournal


class PaperLedgerImportError(RuntimeError):
    """The source paper ledger cannot be safely imported."""


@dataclass(frozen=True)
class PaperLedgerImportReport:
    source_ledger_id: str
    source_events: int
    imported_events: int
    skipped_events: int
    source_chain_verified: bool


def _finite_decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaperLedgerImportError(f"invalid {field} in source ledger") from exc
    if not number.is_finite():
        raise PaperLedgerImportError(f"non-finite {field} in source ledger")
    return number


def _order_summary(order: dict) -> dict:
    keys = (
        "order_id", "client_order_id", "symbol", "side", "quantity",
        "fill_price", "status", "created_at", "filled_quantity",
        "remaining_quantity", "metadata",
    )
    return {key: (_paper_metadata(order.get(key, {})) if key == "metadata" else order.get(key)) for key in keys}


def _working_summary(order: dict) -> dict:
    keys = (
        "order_id", "client_order_id", "symbol", "side", "quantity",
        "limit_price", "filled_quantity", "average_fill_price", "status",
        "created_at", "applied_fill_ids", "metadata",
    )
    return {key: (_paper_metadata(order.get(key, {})) if key == "metadata" else order.get(key)) for key in keys}


def import_paper_ledger(
    source_database_path: str | Path,
    journal: ExecutionObservationJournal,
) -> PaperLedgerImportReport:
    """Import a verified paper ledger without ever opening it for writing."""
    source = Path(source_database_path).expanduser().resolve()
    if not source.is_file():
        raise PaperLedgerImportError("source paper ledger does not exist")

    uri = source.as_uri() + "?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=30)
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            """SELECT seq,created_at,event_type,utc_day,payload,previous_hash,event_hash
            FROM paper_events ORDER BY seq"""
        ).fetchall()
        snapshot_row = db.execute(
            "SELECT payload FROM paper_state WHERE singleton=1"
        ).fetchone()
    except sqlite3.Error as exc:
        raise PaperLedgerImportError("source paper ledger schema or database is invalid") from exc
    finally:
        if "db" in locals():
            db.close()

    if not rows:
        raise PaperLedgerImportError("source paper ledger contains no events")
    if snapshot_row is None:
        raise PaperLedgerImportError("source paper ledger snapshot is missing")

    previous = "GENESIS"
    prepared: list[dict[str, Any]] = []
    for expected_seq, row in enumerate(rows, start=1):
        seq, created_at, event_type, utc_day, payload, previous_hash, event_hash = row
        if seq != expected_seq:
            raise PaperLedgerImportError("source paper ledger sequence has a gap")
        if previous_hash != previous:
            raise PaperLedgerImportError("source paper ledger hash chain is broken")
        expected_hash = hashlib.sha256(
            (previous + "|" + payload).encode("utf-8")
        ).hexdigest()
        if event_hash != expected_hash:
            raise PaperLedgerImportError("source paper ledger event hash is invalid")
        try:
            timestamp = datetime.fromisoformat(created_at)
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("naive source timestamp")
            if timestamp.astimezone(timezone.utc).date().isoformat() != utc_day:
                raise ValueError("UTC day does not match source timestamp")
            event = json.loads(payload)
            state = event["state"]
            if not isinstance(state, dict):
                raise ValueError("state is not an object")
            realized_delta = _finite_decimal(event["realized_delta"], "realized_delta")
            commission_delta = _finite_decimal(event["commission_delta"], "commission_delta")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PaperLedgerImportError(
                f"source paper ledger event {seq} is malformed"
            ) from exc

        orders = state.get("orders", [])
        working = state.get("working", [])
        fill_results = state.get("fill_results", {})
        if not isinstance(orders, list) or not isinstance(working, list):
            raise PaperLedgerImportError(f"source paper ledger event {seq} has invalid order state")
        if not isinstance(fill_results, dict):
            raise PaperLedgerImportError(f"source paper ledger event {seq} has invalid fill state")
        prepared.append({
            "seq": seq,
            "created_at": created_at,
            "event_type": event_type,
            "utc_day": utc_day,
            "event_hash": event_hash,
            "realized_delta": str(realized_delta),
            "commission_delta": str(commission_delta),
            "orders": [_order_summary(item) for item in orders if isinstance(item, dict)],
            "working_orders": [_working_summary(item) for item in working if isinstance(item, dict)],
            "fill_results": {
                fill_id: _order_summary(item)
                for fill_id, item in fill_results.items()
                if isinstance(item, dict)
            },
            "account_snapshot": {
                "balance": state.get("balance"),
                "peak_equity": state.get("peak_equity"),
                "realized_pnl": state.get("realized_pnl"),
                "commission_paid": state.get("commission_paid"),
                "commission_per_side": state.get("commission_per_side"),
                "slippage_bps": state.get("slippage_bps"),
                "last_prices": state.get("last_prices", {}),
                "positions": [
                    {
                        "symbol": item.get("symbol"),
                        "quantity": item.get("quantity"),
                        "average_price": item.get("average_price"),
                        "opened_at": item.get("opened_at"),
                    }
                    for item in state.get("positions", [])
                    if isinstance(item, dict)
                ],
            },
        })
        previous = event_hash

    try:
        latest_state = json.loads(rows[-1][4])["state"]
        stored_state = json.loads(snapshot_row[0])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaperLedgerImportError("source paper ledger snapshot is malformed") from exc
    if latest_state != stored_state:
        raise PaperLedgerImportError("source paper ledger snapshot does not match its audit tail")

    source_ledger_id = rows[0][6]
    imported = 0
    skipped = 0
    for event in prepared:
        event_id = (
            f"paper-ledger:{source_ledger_id}:{event['seq']}:{event['event_hash']}"
        )
        if journal.has_event(event_id):
            skipped += 1
            continue
        journal.append(
            event_id=event_id,
            event_type="paper_ledger_event",
            data={
                "source_ledger_id": source_ledger_id,
                "source_event_seq": event["seq"],
                "source_event_hash": event["event_hash"],
                "source_event_type": event["event_type"],
                "source_created_at": event["created_at"],
                "source_utc_day": event["utc_day"],
                "realized_delta": event["realized_delta"],
                "commission_delta": event["commission_delta"],
                "orders": event["orders"],
                "working_orders": event["working_orders"],
                "fill_results": event["fill_results"],
                "account_snapshot": event["account_snapshot"],
            },
        )
        imported += 1

    return PaperLedgerImportReport(
        source_ledger_id=source_ledger_id,
        source_events=len(prepared),
        imported_events=imported,
        skipped_events=skipped,
        source_chain_verified=True,
    )
