import unittest
from unittest.mock import Mock

from research.paper_state_bridge import commit_paper_cycle, restore_paper_broker


class PaperStateBridgeTests(unittest.TestCase):
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
        store, broker = Mock(), Mock()
        broker.reconcile.return_value = {
            "chain_ok": True, "balance": "100", "open_positions": 0,
            "working_orders": 0, "orders": 0, "events": 1,
        }
        broker.verify_ledger.return_value = True
        broker.export_state.return_value = {"balance": "100", "positions": []}
        broker.ledger_event_count.return_value = 1
        store.commit_cycle.return_value = {"revision": 1, "duplicate": False}
        result = commit_paper_cycle(
            store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
            expected_revision=0, input_fingerprint={"feed": "fixture"},
        )
        self.assertEqual(result["revision"], 1)
        store.commit_cycle.assert_called_once()
        self.assertTrue(store.commit_cycle.call_args.kwargs["events"][0]["payload"]["local_ledger_verified"])

    def test_commit_fails_closed_on_bad_local_ledger(self):
        store, broker = Mock(), Mock()
        broker.reconcile.return_value = {"chain_ok": False}
        with self.assertRaises(RuntimeError):
            commit_paper_cycle(
                store, broker, account_id="acct", run_id="00000000-0000-0000-0000-000000000001",
                expected_revision=0, input_fingerprint={"feed": "fixture"},
            )
        store.commit_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
