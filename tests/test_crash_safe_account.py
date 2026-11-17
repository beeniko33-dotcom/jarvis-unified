"""Crash recovery for the persistent paper account: a failed commit must leave no trace."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from brokers.paper.persistent import CrashInjectedError
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits
from research.execution_observations import ExecutionObservationJournal
from research.persistent_account_audit import audit_account

D0 = date(2026, 11, 10)


def _clock():
    return datetime(D0.year, D0.month, D0.day, 12, tzinfo=timezone.utc)


class CrashSafeAccountTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "acct.sqlite3"

    def tearDown(self):
        self._tmp.cleanup()

    def _open(self) -> PersistentPaperBroker:
        return PersistentPaperBroker(
            Decimal("10000"), database_path=self.db,
            commission_per_side=Decimal("0.1"), clock=_clock,
        )

    def test_crash_before_commit_leaves_no_position_and_audit_stays_clean(self):
        broker = self._open()
        broker.place_order(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "pre-1"))
        broker.inject_crash_before_commit("paper_order")
        with self.assertRaises(CrashInjectedError):
            broker.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("1.25"), "crash-1"))

        reopened = self._open()
        self.assertEqual({p.symbol for p in reopened.get_positions()}, {"EURUSD"})
        self.assertEqual(Decimal(str(reopened.get_account().balance)), Decimal("9999.90"))
        result = audit_account(self.db, as_of=D0)
        self.assertEqual(result["status"], "verified", result["findings"])
        self.assertEqual(result["events"], 2)  # genesis + the one committed order; crash left nothing

    def test_orphaned_client_id_after_crash_can_be_placed_exactly_once_at_broker_level(self):
        broker = self._open()
        broker.inject_crash_before_commit("paper_order")
        with self.assertRaises(CrashInjectedError):
            broker.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("1.25"), "retry-1"))
        reopened = self._open()
        reopened.place_order(OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("1.25"), "retry-1"))
        reopened = self._open()
        self.assertEqual([p.symbol for p in reopened.get_positions()], ["GBPUSD"])
        self.assertEqual(audit_account(self.db, as_of=D0)["status"], "verified")

    def test_crash_inside_execution_is_not_retried_automatically(self):
        """Documents a deliberate limit: the decision journal blocks a same-ID retry after a crash.

        This prevents double execution, but it also means a crashed session cannot resume the same
        orders. An operator must reconcile the prior attempt and use a new client order ID.
        """
        risk = RiskEngine(RiskLimits(Decimal("50"), Decimal("100"), 5, True))
        risk.release_kill_switch(explicit_operator_action=True)
        journal = ExecutionObservationJournal(self.tmp / "obs.sqlite3")
        broker = self._open()
        service = ExecutionService(broker, risk, observation_journal=journal)
        broker.inject_crash_before_commit("paper_order")
        with self.assertRaises(CrashInjectedError):
            service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "sess-x-1"))

        reopened = self._open()
        self.assertEqual(reopened.get_positions(), [])
        retry = ExecutionService(reopened, risk, observation_journal=journal)
        with self.assertRaises(PermissionError):
            retry.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "sess-x-1"))
        retry.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "sess-x-2"))
        self.assertEqual([p.symbol for p in self._open().get_positions()], ["EURUSD"])


if __name__ == "__main__":
    unittest.main()
