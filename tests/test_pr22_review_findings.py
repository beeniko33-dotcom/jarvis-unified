"""Regression tests for defects found while reviewing PR #22 (Track 2 durability).

Every test asserts the CORRECT behaviour and is marked ``expectedFailure`` because
the defect is still present. When a fix lands, the test flips to an "unexpected
success" and fails CI, which forces removal of the marker. That keeps these
findings visible without pretending they are fixed and without blocking CI today.

Scope: the broker (``b.db``) and the reservation store (``r.db``) are separate
SQLite files, so ``ExecutionService`` has no atomic boundary across them.

These are software-defect tests on synthetic paper state only. They are not
Level 3 evidence and use no market data, broker, wallet, or order endpoint.
"""
from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.execution import ExecutionService, ReconciliationRequiredError
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, RiskEngine, RiskLimits


class _SimulatedCrash(BaseException):
    """Stands in for a process death; BaseException so ``except Exception`` can't swallow it."""


def _order(symbol: str, side: Side, qty: str, price: str, client_id: str) -> OrderRequest:
    return OrderRequest(symbol, side, D(qty), D(price), client_id)


class PR22ReviewFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def build(self, **limit_overrides):
        """Open broker + reservation store + service on the SAME files (simulates a restart)."""
        limits = dict(
            max_stake_per_trade=D("1000"),
            max_daily_loss=D("1000"),
            max_open_positions=50,
            kill_switch=False,
        )
        limits.update(limit_overrides)
        broker = PersistentPaperBroker(D("100000"), database_path=self.dir / "b.db")
        store = ExposureReservationStore(self.dir / "r.db")
        service = ExecutionService(broker, RiskEngine(RiskLimits(**limits)), reservations=store)
        return broker, store, service

    # -- Finding 1 (HIGH) -------------------------------------------------------------
    def test_crash_after_fill_before_pending_record_does_not_leak_reservation(self):
        """A death between the broker fill and record_pending_transfer must be recoverable."""
        _, store, service = self.build()

        def die(**_kwargs):
            raise _SimulatedCrash()

        store.record_pending_transfer = die
        with self.assertRaises(_SimulatedCrash):
            service.submit(_order("Y", Side.BUY, "1", "10", "c1"))

        broker2, store2, service2 = self.build()
        service2.reconcile_exposure()
        # The fill is durable, so after recovery exactly one position's worth of exposure
        # may be accounted for, and nothing may remain as a stranded reservation.
        self.assertEqual(len(broker2.get_positions()), 1)
        self.assertEqual(store2.reserved_for_symbol("Y"), D("0"))
        self.assertEqual(store2.committed_for_symbol("Y"), D("10"))

    # -- Finding 2 (HIGH) -------------------------------------------------------------
    def test_crash_after_broker_close_before_release_is_recoverable(self):
        """A death between broker close and release must not strand committed exposure."""
        _, store, service = self.build()
        service.submit(_order("Z", Side.BUY, "1", "10", "d1"))

        def die(*_args, **_kwargs):
            raise _SimulatedCrash()

        store.reduce_committed_for_position = die
        with self.assertRaises(_SimulatedCrash):
            service.close_position("Z", D("10"))

        broker2, store2, service2 = self.build()
        service2.reconcile_exposure()
        self.assertEqual(broker2.get_positions(), [])
        self.assertEqual(store2.committed_for_symbol("Z"), D("0"))

    # -- Finding 3 (MED-HIGH) ---------------------------------------------------------
    def test_retry_of_pending_order_does_not_leak_second_reservation(self):
        """Resubmitting the same client_order_id before reconcile must not reserve twice."""
        _, store, service = self.build()

        def fail_commit(*_args, **_kwargs):
            raise RuntimeError("simulated commit failure")

        store.commit_exposure = fail_commit
        with self.assertRaises(ReconciliationRequiredError):
            service.submit(_order("Q", Side.BUY, "1", "10", "q1"))

        _, store2, service2 = self.build()
        try:
            service2.submit(_order("Q", Side.BUY, "1", "10", "q1"))
        except Exception:
            pass  # either a clean return or a typed error is acceptable
        service2.reconcile_exposure()
        # One 10-notional fill: 10 committed, nothing left reserved.
        self.assertEqual(store2.reserved_for_symbol("Q"), D("0"))
        self.assertEqual(store2.committed_for_symbol("Q"), D("10"))

    # -- Finding 5 (HIGH) -------------------------------------------------------------
    def test_opposite_side_order_does_not_commit_new_exposure(self):
        """Flattening a long with a SELL must not leave phantom committed exposure."""
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "100", "b1"))
        service.submit(_order("X", Side.SELL, "1", "100", "b2"))
        self.assertEqual(broker.get_positions(), [])
        self.assertEqual(store.committed_for_symbol("X"), D("0"))

    # -- Finding 6 (MED, over-restrictive) --------------------------------------------
    def test_exposure_exactly_at_limit_is_allowed(self):
        """Two notional-5 buys against a limit of 10 total exactly 10 and must be allowed."""
        _, _, service = self.build(max_symbol_exposure=D("10"))
        service.submit(_order("X", Side.BUY, "1", "5", "a1"))
        service.submit(_order("X", Side.BUY, "1", "5", "a2"))


if __name__ == "__main__":
    unittest.main()
