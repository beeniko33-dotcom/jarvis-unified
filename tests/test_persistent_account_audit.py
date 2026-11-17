from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from brokers.paper import PersistentPaperBroker
from core.models import OrderRequest, Side
from research.persistent_account_audit import audit_account
from scripts import paper_account_audit, paper_session

D0 = date(2026, 11, 10)


class Clock:
    def __init__(self, day_offset: int = 0, hour: int = 12) -> None:
        self.day_offset, self.hour = day_offset, hour

    def __call__(self) -> datetime:
        base = datetime(D0.year, D0.month, D0.day, self.hour, tzinfo=timezone.utc)
        return base + timedelta(days=self.day_offset)


def _build(path: Path, days: list[int], *, marks_only: list[int] | None = None) -> PersistentPaperBroker:
    clock = Clock()
    broker = PersistentPaperBroker(
        Decimal("10000"), database_path=path, commission_per_side=Decimal("0.1"),
        slippage_bps=Decimal("5"), clock=clock,
    )
    for n, offset in enumerate(days):
        clock.day_offset = offset
        symbol = f"SYM{n}"
        broker.place_order(OrderRequest(symbol, Side.BUY, Decimal("1"), Decimal("1.10"), f"b-{n}"))
        broker.close_position(symbol, Decimal("1.12") if n % 2 == 0 else Decimal("1.08"))
    for offset in marks_only or []:
        clock.day_offset = offset
        broker.set_last_price("EURUSD", Decimal("1.1"))
    return broker


def _rewrite_chain(path: Path, mutate) -> None:
    """Edit events then recompute every hash and the snapshot, as a careful attacker would."""
    with closing(sqlite3.connect(path)) as conn, conn as db:
        rows = db.execute("SELECT seq,payload FROM paper_events ORDER BY seq").fetchall()
        previous = "GENESIS"
        last_state = None
        for seq, payload in rows:
            data = json.loads(payload)
            mutate(seq, data)
            text = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256((previous + "|" + text).encode()).hexdigest()
            db.execute(
                "UPDATE paper_events SET payload=?, previous_hash=?, event_hash=? WHERE seq=?",
                (text, previous, digest, seq),
            )
            previous, last_state = digest, data["state"]
        db.execute(
            "UPDATE paper_state SET payload=?",
            (json.dumps(last_state, sort_keys=True, separators=(",", ":")),),
        )


class AccountAuditTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "acct.sqlite3"

    def tearDown(self):
        self._tmp.cleanup()

    def codes(self, result):
        return {f["code"] for f in result["findings"] if f["severity"] == "error"}

    def test_honest_multi_day_account_verifies(self):
        _build(self.db, [0, 1, 2])
        result = audit_account(self.db, as_of=D0 + timedelta(days=2))
        self.assertEqual(result["status"], "verified", result["findings"])
        self.assertEqual(result["trading_day_coverage"]["current_streak_days"], 3)
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["counts_toward_level_3"])

    def test_account_identity_survives_restart_and_is_stable(self):
        first = _build(self.db, [0])
        account_id = first.account_id()
        self.assertTrue(account_id)
        reopened = PersistentPaperBroker(Decimal("999"), database_path=self.db, clock=Clock(1))
        self.assertEqual(reopened.account_id(), account_id)
        self.assertEqual(audit_account(self.db, as_of=D0)["account_id"], account_id)

    def test_new_accounts_get_distinct_identities(self):
        a = _build(self.tmp / "a.sqlite3", [0]).account_id()
        b = _build(self.tmp / "b.sqlite3", [0]).account_id()
        self.assertNotEqual(a, b)

    def test_restart_continues_one_account_with_no_reset(self):
        _build(self.db, [0])
        reopened = PersistentPaperBroker(Decimal("1"), database_path=self.db, clock=Clock(1))
        reopened.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "next-1"))
        reopened.close_position("EURUSD", Decimal("1.11"))
        result = audit_account(self.db, as_of=D0 + timedelta(days=1))
        self.assertEqual(result["status"], "verified", result["findings"])
        self.assertEqual(result["totals"]["starting_balance"], "10000")  # the 1 was ignored

    def test_missing_day_is_reported_and_resets_the_streak(self):
        _build(self.db, [0, 1, 3])
        result = audit_account(self.db, as_of=D0 + timedelta(days=3))
        coverage = result["trading_day_coverage"]
        self.assertEqual(coverage["missing_days"], [(D0 + timedelta(days=2)).isoformat()])
        self.assertEqual(coverage["current_streak_days"], 1)
        self.assertEqual(result["status"], "verified")  # integrity is fine; coverage is a warning
        self.assertTrue(any(f["code"] == "coverage" for f in result["findings"]))

    def test_mark_updates_alone_do_not_count_as_a_session_day(self):
        _build(self.db, [0], marks_only=[1])
        result = audit_account(self.db, as_of=D0 + timedelta(days=1))
        self.assertEqual(result["trading_day_coverage"]["last_session_day"], D0.isoformat())
        self.assertEqual(result["trading_day_coverage"]["state"], "missing_today")
        self.assertEqual(result["days_with_only_mark_updates"], [(D0 + timedelta(days=1)).isoformat()])

    def test_edited_event_breaks_the_chain(self):
        _build(self.db, [0, 1])
        with closing(sqlite3.connect(self.db)) as conn, conn as db:
            db.execute("UPDATE paper_events SET payload=replace(payload,'\"1.10\"','\"9.99\"') WHERE seq=2")
        self.assertIn("chain_broken", self.codes(audit_account(self.db, as_of=D0 + timedelta(days=1))))

    def test_edited_snapshot_is_caught(self):
        _build(self.db, [0])
        with closing(sqlite3.connect(self.db)) as conn, conn as db:
            payload = json.loads(db.execute("SELECT payload FROM paper_state").fetchone()[0])
            payload["balance"] = "999999"
            db.execute("UPDATE paper_state SET payload=?", (json.dumps(payload),))
        self.assertIn("snapshot_mismatch", self.codes(audit_account(self.db, as_of=D0)))

    def test_rehashed_balance_edit_is_caught_by_continuity(self):
        _build(self.db, [0, 1])

        def bump(seq, data):
            if seq == 3:
                data["state"]["balance"] = str(Decimal(data["state"]["balance"]) + Decimal("50"))

        _rewrite_chain(self.db, bump)
        result = audit_account(self.db, as_of=D0 + timedelta(days=1))
        self.assertEqual(result["status"], "failed")
        self.assertIn("balance_discontinuity", self.codes(result))

    def test_silent_reset_with_a_consistent_rewrite_needs_an_anchor(self):
        """Documents the limit: only an external anchor catches a fully consistent rewrite."""
        _build(self.db, [0, 1])
        before = audit_account(self.db, as_of=D0 + timedelta(days=1))
        anchor = {"account_id": before["account_id"], **before["head"]}

        def shift_all(_seq, data):
            data["state"]["balance"] = str(Decimal(data["state"]["balance"]) + Decimal("100"))

        _rewrite_chain(self.db, shift_all)
        without_anchor = audit_account(self.db, as_of=D0 + timedelta(days=1))
        self.assertEqual(without_anchor["status"], "verified")  # internally consistent
        with_anchor = audit_account(self.db, as_of=D0 + timedelta(days=1), anchors=[anchor])
        self.assertEqual(with_anchor["status"], "failed")
        self.assertIn("anchor_mismatch", self.codes(with_anchor))

    def test_anchor_from_a_different_account_is_rejected(self):
        _build(self.db, [0])
        other = _build(self.tmp / "other.sqlite3", [0])
        info = audit_account(self.tmp / "other.sqlite3", as_of=D0)
        anchor = {"account_id": other.account_id(), **info["head"]}
        result = audit_account(self.db, as_of=D0, anchors=[anchor])
        self.assertIn("anchor_identity_mismatch", self.codes(result))

    def test_legacy_account_without_identity_is_a_warning_not_an_error(self):
        _build(self.db, [0])
        _rewrite_chain(self.db, lambda _s, data: data.pop("account_id", None))
        result = audit_account(self.db, as_of=D0)
        self.assertEqual(result["status"], "verified")
        self.assertIsNone(result["account_id"])
        self.assertTrue(any(f["code"] == "legacy_no_account_id" for f in result["findings"]))

    def test_injected_identity_after_genesis_is_rejected(self):
        _build(self.db, [0])
        _rewrite_chain(self.db, lambda seq, data: data.update(account_id="evil") if seq == 2 else None)
        self.assertIn("identity_changed", self.codes(audit_account(self.db, as_of=D0)))

    def test_open_position_at_end_is_flagged(self):
        broker = _build(self.db, [0])
        broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "open-1"))
        result = audit_account(self.db, as_of=D0)
        self.assertEqual(result["open_positions_at_end"], 1)
        self.assertTrue(any(f["code"] == "open_positions" for f in result["findings"]))

    def test_audit_is_read_only(self):
        _build(self.db, [0, 1])
        before = self.db.read_bytes()
        audit_account(self.db, as_of=D0 + timedelta(days=1))
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_or_foreign_database_is_an_error_not_a_new_account(self):
        with self.assertRaises(FileNotFoundError):
            audit_account(self.tmp / "nope.sqlite3")
        self.assertFalse((self.tmp / "nope.sqlite3").exists())
        junk = self.tmp / "junk.sqlite3"
        junk.write_bytes(b"not a database at all, just bytes")
        with self.assertRaises(ValueError):
            audit_account(junk)

    def test_cli_exit_codes_and_append_only_anchor_file(self):
        _build(self.db, [0, 1])
        anchors = self.tmp / "anchors.jsonl"
        as_of = (D0 + timedelta(days=1)).isoformat()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paper_account_audit.main([str(self.db), "--as-of", as_of, "--anchor-file", str(anchors)]), 0)
            self.assertEqual(paper_account_audit.main([str(self.db), "--as-of", as_of, "--anchor-file", str(anchors)]), 0)
        self.assertEqual(len(anchors.read_text().splitlines()), 1)  # unchanged head: not re-appended
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paper_account_audit.main([str(self.db), "--as-of", (D0 + timedelta(days=5)).isoformat()]), 2)
        original = anchors.read_text()
        with closing(sqlite3.connect(self.db)) as conn, conn as db:
            db.execute("UPDATE paper_events SET payload=replace(payload,'\"1.10\"','\"9.99\"') WHERE seq=2")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paper_account_audit.main([str(self.db), "--as-of", as_of, "--anchor-file", str(anchors)]), 2)
        self.assertEqual(anchors.read_text(), original)  # nothing appended after a failed audit


class SessionRunnerAccountTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        argv = ["paper_session.py", "--allow-entries", "--account-db", str(self.tmp / "acct.sqlite3")]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(paper_session.main(), 0)
        return json.loads(out.getvalue())

    def test_same_day_rerun_is_idempotent_and_keeps_one_account(self):
        day_before = datetime.now(timezone.utc).date()
        first = self._run()
        second = self._run()
        if datetime.now(timezone.utc).date() != day_before:
            self.skipTest("crossed UTC midnight during the test")
        self.assertEqual(first["account_id"], second["account_id"])
        rejected = [e for e in second["events"] if e["event"] == "rejected"]
        self.assertEqual(len(rejected), 2)
        self.assertFalse([e for e in second["events"] if e["event"] == "fill"])
        with closing(sqlite3.connect(self.tmp / "acct.sqlite3")) as conn:
            orders = conn.execute("SELECT COUNT(*) FROM paper_events WHERE event_type='paper_order'").fetchone()[0]
        self.assertEqual(orders, 2)
        audit = audit_account(self.tmp / "acct.sqlite3")
        self.assertEqual(audit["status"], "verified", audit["findings"])

    def test_jsonl_mode_is_unchanged_by_default(self):
        argv = ["paper_session.py", "--allow-entries", "--ledger", str(self.tmp / "l.jsonl")]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            paper_session.main()
        result = json.loads(out.getvalue())
        self.assertIsNone(result["account_db"])
        self.assertTrue((self.tmp / "l.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
