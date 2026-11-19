from __future__ import annotations

import os
import unittest
from uuid import uuid4

import psycopg

from research.supabase_paper_state import (
    PaperStateConflict,
    SupabasePaperStateStore,
)


DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "requires disposable PostgreSQL service")
class PostgresPaperLedgerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.account_id = "it-" + uuid4().hex
        self.store = SupabasePaperStateStore(dsn=DATABASE_URL)

    def cycle(self, *, run_id=None, revision=0, state=None, fingerprint=None):
        return {
            "account_id": self.account_id,
            "run_id": run_id or str(uuid4()),
            "expected_revision": revision,
            "state": state or {"schema_version": 1, "marker": "initial"},
            "events": [{"event_type": "research.decision", "payload": {"orders_submitted": 0}}],
            "input_fingerprint": fingerprint or {"snapshot": "snapshot-a"},
            "metadata": {"mode": "paper"},
        }

    def test_atomic_commit_and_restart_recovery(self):
        result = self.store.commit_cycle(**self.cycle())
        self.assertEqual(result["revision"], 1)
        self.assertFalse(result["duplicate"])
        recovered = SupabasePaperStateStore(dsn=DATABASE_URL).load_account(self.account_id)
        self.assertEqual(recovered["revision"], 1)
        self.assertEqual(recovered["state"]["marker"], "initial")
        ledger = self.store.verify_ledger(self.account_id)
        self.assertTrue(ledger["verified"])
        self.assertEqual(ledger["events"], 1)

    def test_duplicate_after_later_revision_is_a_noop(self):
        first = self.cycle(
            state={"schema_version": 1, "marker": "first"},
            fingerprint={"snapshot": "same-input"},
        )
        first_result = self.store.commit_cycle(**first)
        second = self.cycle(
            revision=1,
            state={"schema_version": 1, "marker": "second"},
            fingerprint={"snapshot": "later-input"},
        )
        self.store.commit_cycle(**second)
        replay = dict(first)
        replay["expected_revision"] = 2
        replay["state"] = {"schema_version": 1, "marker": "different-proposed-state"}
        duplicate = self.store.commit_cycle(**replay)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["run_revision"], 1)
        self.assertEqual(duplicate["revision"], 2)
        self.assertEqual(duplicate["state_sha256"], first_result["state_sha256"])
        account = self.store.load_account(self.account_id)
        self.assertEqual(account["state"]["marker"], "second")
        self.assertEqual(self.store.verify_ledger(self.account_id)["events"], 2)

    def test_same_run_id_with_conflicting_input_is_rejected(self):
        values = self.cycle()
        self.store.commit_cycle(**values)
        conflict = dict(values)
        conflict["input_fingerprint"] = {"snapshot": "tampered-input"}
        with self.assertRaises(PaperStateConflict):
            self.store.commit_cycle(**conflict)

    def test_failure_during_ledger_insert_rolls_back_run_and_snapshot(self):
        trigger_name = "it_fail_" + uuid4().hex
        function_name = "it_fail_fn_" + uuid4().hex
        with psycopg.connect(DATABASE_URL, autocommit=True) as db:
            with db.cursor() as cur:
                cur.execute(f"""
                    create function jarvis_private.{function_name}()
                    returns trigger language plpgsql as $$
                    begin
                        if new.account_id = '{self.account_id}' then
                            raise exception 'injected paper ledger failure';
                        end if;
                        return new;
                    end;
                    $$;
                """)
                cur.execute(f"""
                    create trigger {trigger_name}
                    before insert on jarvis_private.paper_ledger_events
                    for each row execute function jarvis_private.{function_name}();
                """)
        try:
            with self.assertRaises(Exception):
                self.store.commit_cycle(**self.cycle())
        finally:
            with psycopg.connect(DATABASE_URL, autocommit=True) as db:
                with db.cursor() as cur:
                    cur.execute(f"drop trigger if exists {trigger_name} on jarvis_private.paper_ledger_events")
                    cur.execute(f"drop function if exists jarvis_private.{function_name}()")
        with psycopg.connect(DATABASE_URL) as db:
            with db.cursor() as cur:
                cur.execute("select count(*) from jarvis_private.paper_accounts where account_id=%s",
                            (self.account_id,))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute("select count(*) from jarvis_private.paper_runs where account_id=%s",
                            (self.account_id,))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute("select count(*) from jarvis_private.paper_ledger_events where account_id=%s",
                            (self.account_id,))
                self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
