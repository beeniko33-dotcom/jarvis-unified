"""Explicit adapter between the durable SQLite paper broker and Supabase paper state.

Callers must run this only in paper mode after a completed, locally reconciled cycle.
No live broker interface is imported or exposed here.
"""
from __future__ import annotations

from typing import Any


def restore_paper_broker(store: Any, broker: Any, account_id: str) -> int:
    """Verify and restore the remote snapshot; return its revision (zero if new)."""
    remote = store.load_account(account_id)
    if remote is None:
        return 0
    if remote.get("mode") != "paper":
        raise RuntimeError("refusing to restore a non-paper account")
    broker.restore_state(remote["state"])
    return int(remote["revision"])


def commit_paper_cycle(
    store: Any,
    broker: Any,
    *,
    account_id: str,
    run_id: str,
    expected_revision: int,
    input_fingerprint: dict,
    metadata: dict | None = None,
) -> dict:
    """Commit a locally reconciled broker snapshot and a verification event remotely."""
    reconciliation = broker.reconcile()
    if reconciliation.get("chain_ok") is not True:
        raise RuntimeError("local paper broker ledger is not verified")
    if broker.verify_ledger() is not True:
        raise RuntimeError("local paper broker ledger verification failed")
    state = broker.export_state()
    return store.commit_cycle(
        account_id=account_id,
        run_id=run_id,
        expected_revision=expected_revision,
        state=state,
        events=[{
            "event_type": "cycle.completed",
            "payload": {
                "local_ledger_events": broker.ledger_event_count(),
                "local_ledger_verified": True,
                "reconciliation": {
                    "balance": reconciliation["balance"],
                    "open_positions": reconciliation["open_positions"],
                    "working_orders": reconciliation["working_orders"],
                    "orders": reconciliation["orders"],
                    "events": reconciliation["events"],
                },
            },
        }],
        input_fingerprint=input_fingerprint,
        metadata=metadata or {"mode": "paper", "source": "persistent-paper-broker"},
    )
