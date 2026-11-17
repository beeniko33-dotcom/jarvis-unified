"""Bounded real-Postgres smoke test for the paper-state bridge.

Creates one uniquely named synthetic paper account and one completed cycle.
No external broker, market feed, or live-order path is imported.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from brokers.paper.persistent import PersistentPaperBroker
from research.paper_state_bridge import commit_paper_cycle, restore_paper_broker
from research.supabase_paper_state import PaperStateConflict, SupabasePaperStateStore


def main() -> None:
    if not os.environ.get("JARVIS_DATABASE_URL"):
        raise SystemExit("JARVIS_DATABASE_URL is required")
    suffix = uuid4().hex
    account_id = f"prototype-smoke-{suffix}"
    run_id = str(uuid4())
    store = SupabasePaperStateStore()

    with tempfile.TemporaryDirectory(prefix="jarvis-supabase-smoke-") as tmp:
        local_path = Path(tmp) / "runner-a.sqlite"
        fresh_path = Path(tmp) / "runner-b.sqlite"
        broker = PersistentPaperBroker(database_path=local_path)

        committed = commit_paper_cycle(
            store,
            broker,
            account_id=account_id,
            run_id=run_id,
            expected_revision=0,
            input_fingerprint={
                "kind": "synthetic_prototype_smoke",
                "scenario_id": suffix,
                "market_data_used": False,
                "external_orders_sent": False,
            },
            metadata={"purpose": "bounded_integration_validation", "mode": "paper"},
        )
        assert committed["revision"] == 1 and committed["duplicate"] is False
        remote = store.load_account(account_id)
        assert remote is not None and remote["revision"] == 1
        assert remote["mode"] == "paper"

        restored = PersistentPaperBroker(database_path=fresh_path)
        restored_revision = restore_paper_broker(store, restored, account_id)
        assert restored_revision == 1
        assert restored.export_state() == remote["state"]
        assert restored.verify_ledger() is True

        duplicate = commit_paper_cycle(
            store,
            broker,
            account_id=account_id,
            run_id=run_id,
            expected_revision=0,
            input_fingerprint={
                "kind": "synthetic_prototype_smoke",
                "scenario_id": suffix,
                "market_data_used": False,
                "external_orders_sent": False,
            },
            metadata={"purpose": "bounded_integration_validation", "mode": "paper"},
        )
        assert duplicate["duplicate"] is True

        try:
            store.commit_cycle(
                account_id=account_id,
                run_id=str(uuid4()),
                expected_revision=0,
                state=remote["state"],
                events=[{"event_type": "cycle.stale_revision_probe", "payload": {"probe": True}}],
                input_fingerprint={"kind": "stale_revision_probe", "scenario_id": suffix},
                metadata={"mode": "paper"},
            )
        except PaperStateConflict:
            pass
        else:
            raise AssertionError("stale revision was not rejected")

        integrity = store.verify_ledger(account_id)
        final = store.load_account(account_id)
        assert final is not None and final["revision"] == 1
        assert integrity["events"] >= 1
        print("Supabase paper integration: PASS")
        print("Account mode: paper")
        print("Committed revision: 1")
        print("Duplicate run: rejected as idempotent")
        print("Stale revision: rejected")
        print("Fresh-runner restore: verified")
        print("Remote ledger integrity: verified")
        print("External broker orders: none")
        print("Synthetic account id: " + account_id)


if __name__ == "__main__":
    main()
