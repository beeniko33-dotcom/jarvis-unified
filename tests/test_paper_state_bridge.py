import unittest
from unittest.mock import Mock

from research.paper_state_bridge import commit_paper_cycle, restore_paper_broker


class PaperStateBridgeTests(unittest.TestCase):
    def _valid_broker(self, state):
        broker = Mock()
        broker.reconcile.return_value = {
            "chain_ok": True, "balance": "100", "open_positions": 1,
            "working_orders": 0, "orders": len(state.get("orders", [])), "events": 2,
        }
        broker.verify_ledger.return_value = True
        broker.export_state.return_value = state
        broker.ledger_event_count.return_value = 2
        return broker

    def test_restore_verifies_and_restores_remote_paper_state(self):
        store, broker = Mock(), Mock()
        store.load_account.return_value = {"mode": "paper", "revision": 7, "state": {"balance": "100"}}
        self.assertEqual(restore_paper_broker(store, broker, "acct"), 7)
        broker.restore_state.assert_called_once_with({"balance": "100"})

    def test_new_account_starts_at_revision_zero(self):
        store, broker = Mock(), Mock()
        store.load_account.return_value = None
        self.assertEqual(restore_paper_broker(store, broker, "acct"), 0)
        broker.restore_state.assert_not_called()

    def test_commit_requires_local_reconciliation_and_ledger_verification(self):
        store = Mock()
        store.load_account.return_value = None
        broker = self._valid_broker({"balance": "100", "positions": [], "orders": []})
        store.commit_cycle.return_value = {"revision": 1, "duplicate": False}
        result = commit_paper_cycle(
            store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
            expected_revision=0, input_fingerprint={"feed": "fixture"},
        )
        self.assertEqual(result["revision"], 1)
        events = store.commit_cycle.call_args.kwargs["events"]
        self.assertEqual([e["event_type"] for e in events], ["position.snapshot", "cycle.completed"])
        self.assertTrue(events[-1]["payload"]["local_ledger_verified"])

    def test_commit_persists_order_and_fill_lifecycle(self):
        store = Mock()
        store.load_account.return_value = None
        state = {
            "balance": "99.9", "positions": [{"symbol": "BTC_USDT", "quantity": "0.001"}],
            "orders": [{
                "order_id": "order-1", "client_order_id": "client-1", "symbol": "BTC_USDT",
                "side": "buy", "quantity": "0.001", "filled_quantity": "0.001",
                "remaining_quantity": "0", "fill_price": "60000", "status": "filled",
                "created_at": "2026-11-19T08:00:00+00:00", "metadata": {"research_lineage": {"quote_source": "gateio_public_spot"}},
            }],
        }
        broker = self._valid_broker(state)
        store.commit_cycle.return_value = {"revision": 1, "duplicate": False}
        commit_paper_cycle(
            store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
            expected_revision=0, input_fingerprint={"feed": "gateio"},
        )
        events = store.commit_cycle.call_args.kwargs["events"]
        self.assertEqual([e["event_type"] for e in events], [
            "order.submitted", "order.filled", "position.snapshot", "cycle.completed",
        ])
        self.assertEqual(events[1]["payload"]["order_id"], "order-1")

    def test_commit_emits_only_incremental_fill_update_for_existing_order(self):
        store = Mock()
        store.load_account.return_value = {
            "mode": "paper", "revision": 3,
            "state": {"orders": [{
                "order_id": "order-1", "status": "open", "filled_quantity": "0.002",
                "quantity": "0.01",
            }]},
        }
        state = {"balance": "99", "positions": [], "orders": [{
            "order_id": "order-1", "client_order_id": "client-1", "symbol": "ETH_USDT",
            "side": "buy", "quantity": "0.01", "filled_quantity": "0.005",
            "remaining_quantity": "0.005", "fill_price": "3000", "status": "partially_filled",
            "created_at": "2026-11-19T08:00:00+00:00", "metadata": {},
        }]}
        broker = self._valid_broker(state)
        store.commit_cycle.return_value = {"revision": 4, "duplicate": False}
        commit_paper_cycle(
            store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000004",
            expected_revision=3, input_fingerprint={"feed": "gateio"},
        )
        events = store.commit_cycle.call_args.kwargs["events"]
        self.assertEqual([e["event_type"] for e in events], [
            "order.status_changed", "order.fill_updated", "position.snapshot", "cycle.completed",
        ])
        self.assertEqual(events[1]["payload"]["previous_filled_quantity"], "0.002")

    def test_commit_rejects_stale_remote_revision_before_write(self):
        store = Mock()
        store.load_account.return_value = {"mode": "paper", "revision": 4, "state": {"orders": []}}
        broker = self._valid_broker({"balance": "100", "positions": [], "orders": []})
        with self.assertRaisesRegex(RuntimeError, "revision changed"):
            commit_paper_cycle(
                store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
                expected_revision=3, input_fingerprint={"feed": "fixture"},
            )
        store.commit_cycle.assert_not_called()

    def test_commit_fails_closed_on_bad_local_ledger(self):
        store, broker = Mock(), Mock()
        broker.reconcile.return_value = {"chain_ok": False}
        with self.assertRaises(RuntimeError):
            commit_paper_cycle(
                store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
                expected_revision=0, input_fingerprint={"feed": "fixture"},
            )
        store.load_account.assert_not_called()
        store.commit_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
