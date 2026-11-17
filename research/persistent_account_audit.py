"""Read-only audit of a PersistentPaperBroker SQLite account across its whole history.

Opens the database read-only (it can never create, repair or reset an account) and checks:

- the SHA-256 event chain, recomputed independently;
- that the stored snapshot equals the final event's state;
- accounting continuity between every pair of consecutive events: the balance moves by exactly
  realized P&L minus commission, and cumulative realized P&L and commission move by the recorded
  deltas (so edits, gaps and silent resets are detected);
- timestamp ordering and that each event's ``utc_day`` matches its timestamp;
- account identity (a UUID fixed in the hash-chained genesis event of new accounts);
- UTC-day coverage of real trading events (``paper_*``), reported via the shared day assessment.

Limits, stated so a clean result is not over-read:
- A chain that was rewritten end to end with consistent hashes is internally valid. Detecting that
  needs an external anchor: record ``head`` somewhere the database host cannot edit, and pass the
  records back via ``anchors`` on later runs.
- Equity and unrealized P&L need market marks and are not recomputed here.
- This proves account integrity. It does not prove market-data authenticity or strategy quality,
  and it never counts toward the Level 3 gate.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

from research.day_coverage import assess_days

_TRADING_PREFIX = "paper_"


def _finding(severity: str, code: str, message: str, seq: int | None = None) -> dict[str, Any]:
    finding: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if seq is not None:
        finding["seq"] = seq
    return finding


def _dec(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return number


def _open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"account database not found: {path}")
    # Quote the path so characters such as '?' or '#' cannot be read as URI syntax.
    return sqlite3.connect(f"file:{quote(path.resolve().as_posix())}?mode=ro", uri=True, timeout=30)


def audit_account(
    database_path: str | Path,
    *,
    as_of: date | None = None,
    anchors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit the account at ``database_path``. ``as_of`` defaults to today in UTC."""
    path = Path(database_path)
    as_of = as_of or datetime.now(timezone.utc).date()
    findings: list[dict[str, Any]] = []

    with closing(_open_readonly(path)) as db:
        try:
            events = db.execute(
                "SELECT seq,created_at,event_type,utc_day,payload,previous_hash,event_hash "
                "FROM paper_events ORDER BY seq"
            ).fetchall()
            state_row = db.execute("SELECT payload FROM paper_state WHERE singleton=1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"not a Jarvis paper account database: {exc}") from exc

    if not events:
        return {"status": "failed", "findings": [_finding("error", "no_events", "account has no events")]}

    # 1. Hash chain, recomputed independently of the broker class.
    previous = "GENESIS"
    chain_ok = True
    for seq, _created, _type, _day, payload, prev_hash, digest in events:
        expected = hashlib.sha256((previous + "|" + payload).encode()).hexdigest()
        if prev_hash != previous or digest != expected:
            findings.append(_finding("error", "chain_broken", "event hash chain is broken here", seq))
            chain_ok = False
            break
        previous = digest
    head = {"seq": events[-1][0], "event_hash": events[-1][6]}

    parsed: list[dict[str, Any]] = []
    if chain_ok:
        try:
            parsed = [json.loads(row[4]) for row in events]
        except json.JSONDecodeError:
            findings.append(_finding("error", "payload_malformed", "an event payload is not valid JSON"))
            chain_ok = False

    account_id: str | None = None
    trading_days: list[date] = []
    mark_only_days: set[str] = set()
    open_positions = working_orders = 0
    totals: dict[str, str] = {}

    if chain_ok:
        # 2. Snapshot equals final event state.
        if state_row is None or json.loads(state_row[0]) != parsed[-1].get("state"):
            findings.append(
                _finding("error", "snapshot_mismatch", "stored snapshot differs from the final event", events[-1][0])
            )

        # 3. Identity.
        genesis = parsed[0]
        value = genesis.get("account_id")
        account_id = value if isinstance(value, str) else None
        if account_id is None:
            findings.append(
                _finding("warning", "legacy_no_account_id", "account predates identities; none is recorded")
            )
        if any("account_id" in item for item in parsed[1:]):
            findings.append(_finding("error", "identity_changed", "account_id appears after the genesis event"))
        if events[0][2] != "initialized":
            findings.append(_finding("error", "bad_genesis", "first event is not 'initialized'", events[0][0]))

        # 4. Continuity and timestamps.
        last_time: datetime | None = None
        for index, (row, payload) in enumerate(zip(events, parsed)):
            seq, created_at, event_type, utc_day = row[0], row[1], row[2], row[3]
            try:
                stamp = datetime.fromisoformat(created_at)
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("naive timestamp")
                stamp = stamp.astimezone(timezone.utc)
            except ValueError:
                findings.append(_finding("error", "bad_timestamp", "timestamp is missing a timezone or malformed", seq))
                continue
            if last_time is not None and stamp < last_time:
                findings.append(_finding("error", "time_went_backwards", "event is older than its predecessor", seq))
            last_time = stamp
            if stamp.date().isoformat() != utc_day:
                findings.append(_finding("error", "utc_day_mismatch", "utc_day does not match the timestamp", seq))

            if event_type.startswith(_TRADING_PREFIX):
                trading_days.append(stamp.date())
            elif event_type == "mark_price":
                mark_only_days.add(stamp.date().isoformat())

            if index == 0:
                continue
            try:
                state, before = payload["state"], parsed[index - 1]["state"]
                realized_delta = _dec(payload["realized_delta"])
                commission_delta = _dec(payload["commission_delta"])
                balance_step = _dec(state["balance"]) - _dec(before["balance"])
                realized_step = _dec(state["realized_pnl"]) - _dec(before["realized_pnl"])
                commission_step = _dec(state["commission_paid"]) - _dec(before["commission_paid"])
            except (KeyError, ValueError, TypeError):
                findings.append(_finding("error", "state_malformed", "event state lacks valid accounting fields", seq))
                continue
            if realized_step != realized_delta:
                findings.append(_finding("error", "realized_discontinuity", "realized P&L step differs from its delta", seq))
            if commission_step != commission_delta:
                findings.append(_finding("error", "commission_discontinuity", "commission step differs from its delta", seq))
            if balance_step != realized_delta - commission_delta:
                findings.append(
                    _finding("error", "balance_discontinuity", "balance moved by more than P&L minus commission", seq)
                )

        final = parsed[-1].get("state", {})
        open_positions = len(final.get("positions", []))
        working_orders = len(final.get("working", []))
        totals = {
            "starting_balance": str(parsed[0].get("state", {}).get("balance")),
            "balance": str(final.get("balance")),
            "realized_pnl": str(final.get("realized_pnl")),
            "commission_paid": str(final.get("commission_paid")),
        }
        if open_positions:
            findings.append(_finding("warning", "open_positions", f"{open_positions} position(s) open at end"))
        if working_orders:
            findings.append(_finding("warning", "working_orders", f"{working_orders} working order(s) at end"))

    # 5. External anchors: every previously recorded (seq, hash) must still be in the chain.
    anchors_checked = 0
    if chain_ok and anchors:
        by_seq = {row[0]: row[6] for row in events}
        for anchor in anchors:
            anchors_checked += 1
            if anchor.get("account_id") != account_id:
                findings.append(_finding("error", "anchor_identity_mismatch", f"anchor seq {anchor.get('seq')} belongs to a different account"))
            elif by_seq.get(anchor.get("seq")) != anchor.get("event_hash"):
                findings.append(
                    _finding("error", "anchor_mismatch", "history differs from a previously recorded anchor", anchor.get("seq"))
                )

    coverage = assess_days(trading_days, as_of) if trading_days else None
    if coverage is None:
        findings.append(_finding("warning", "no_trading_days", "no trading events recorded yet"))
    else:
        for alert in coverage["alerts"]:
            findings.append(_finding("warning", "coverage", alert))

    errors = [item for item in findings if item["severity"] == "error"]
    return {
        "status": "failed" if errors else "verified",
        "as_of_utc_date": as_of.isoformat(),
        "account_id": account_id,
        "events": len(events),
        "head": head,
        "anchors_checked": anchors_checked,
        "totals": totals,
        "open_positions_at_end": open_positions,
        "working_orders_at_end": working_orders,
        "trading_day_coverage": coverage,
        "days_with_only_mark_updates": sorted(mark_only_days - {d.isoformat() for d in trading_days}),
        "findings": findings,
        "counts_toward_level_3": False,
        "note": (
            "Account-integrity audit only. It does not prove market-data authenticity or "
            "strategy quality, and trading days here never count toward the Level 3 gate."
        ),
    }
