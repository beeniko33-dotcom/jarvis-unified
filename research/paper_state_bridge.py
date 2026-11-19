"""Explicit adapter between the durable SQLite paper broker and Supabase paper state.

Callers must run this only in paper mode after a completed, locally reconciled cycle.
No live broker interface is imported or exposed here. Remote ledger events describe
order/fill/position lifecycle deltas, not merely a repeated end-of-cycle snapshot.
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


def _order_events(previous_state: dict | None, current_state: dict) -> list[dict]:
    """Build append-only lifecycle deltas by comparing verified account snapshots."""
    previous_orders = {
        item["order_id"]: item for item in (previous_state or {}).get("orders", [])
        if isinstance(item, dict) and isinstance(item.get("order_id"), str)
    }
    events: list[dict] = []
    for order in current_state.get("orders", []):
        if not isinstance(order, dict) or not isinstance(order.get("order_id"), str):
            raise RuntimeError("paper broker exported a malformed order")
        order_id = order["order_id"]
        prior = previous_orders.get(order_id)
        common = {
            "order_id": order_id,
            "client_order_id": order.get("client_order_id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "quantity": order.get("quantity"),
            "status": order.get("status"),
            "fill_price": order.get("fill_price"),
            "filled_quantity": order.get("filled_quantity", order.get("quantity")),
            "remaining_quantity": order.get("remaining_quantity", "0"),
            "metadata": order.get("metadata", {}),
        }
        if prior is None:
            events.append({
                "event_type": "order.submitted",
                "occurred_at": order.get("created_at"),
                "payload": common,
            })
            filled = str(common["filled_quantity"] or "0")
            if filled not in {"0", "0.0", "0.00"}:
                events.append({
                    "event_type": "order.filled" if common["status"] == "filled" else "order.partially_filled",
                    "occurred_at": order.get("created_at"),
                    "payload": common,
                })
            continue

        old_filled = str(prior.get("filled_quantity", prior.get("quantity", "0")))
        new_filled = str(common["filled_quantity"] or "0")
        if prior.get("status") != common["status"]:
            events.append({
                "event_type": "order.status_changed",
                "occurred_at": order.get("created_at"),
                "payload": {**common, "previous_status": prior.get("status")},
            })
        if old_filled != new_filled:
            events.append({
                "event_type": "order.fill_updated",
                "occurred_at": order.get("created_at"),
                "payload": {
                    **common,
                    "previous_filled_quantity": old_filled,
                    "filled_quantity": new_filled,
                },
            })
    return events


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
    """Commit a locally reconciled broker snapshot and lifecycle events remotely."""
    reconciliation = broker.reconcile()
    if reconciliation.get("chain_ok") is not True:
        raise RuntimeError("local paper broker ledger is not verified")
    if broker.verify_ledger() is not True:
        raise RuntimeError("local paper broker ledger verification failed")

    # load_account validates remote state hash and the complete remote ledger chain.
    previous = store.load_account(account_id)
    if previous is not None and previous.get("mode") != "paper":
        raise RuntimeError("refusing to append to a non-paper account")
    previous_state = previous["state"] if previous else None
    state = broker.export_state()
    events = _order_events(previous_state, state)
    events.append({
        "event_type": "position.snapshot",
        "payload": {
            "positions": state.get("positions", []),
            "balance": reconciliation.get("balance"),
            "open_positions": reconciliation.get("open_positions"),
            "working_orders": reconciliation.get("working_orders"),
            "orders": reconciliation.get("orders"),
        },
    })
    events.append({
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
    })
    return store.commit_cycle(
        account_id=account_id,
        run_id=run_id,
        expected_revision=expected_revision,
        state=state,
        events=events,
        input_fingerprint=input_fingerprint,
        metadata=metadata or {"mode": "paper", "source": "persistent-paper-broker"},
    )
