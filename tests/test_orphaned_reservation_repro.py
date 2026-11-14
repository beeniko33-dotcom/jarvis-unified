"""Repro: a crash between place_order() and record_pending_transfer() leaks
the reservation permanently, because submit() creates it with ttl_seconds=None
and reconcile_exposure() only inspects pending transfers/releases.

The fill itself is unrecoverable with an in-memory broker (it exists only in
broker memory), but the *reservation* must not consume capacity forever.
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from decimal import Decimal

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, RiskEngine, RiskLimits


class OrphanedReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = pathlib.Path(self._tmp.name) / "r.sqlite3"

    def _service(self, cap: str = "30") -> ExecutionService:
        store = ExposureReservationStore(self.db)
        broker = PaperBroker(Decimal("1000"))
        risk = RiskEngine(
            RiskLimits(Decimal("50"), Decimal("100"), 5, False,
                       max_symbol_exposure=Decimal(cap))
        )
        return ExecutionService(broker, risk, reservations=store)

    def test_crash_before_pending_transfer_does_not_leak_capacity(self) -> None:
        service = self._service(cap="30")
        store = service.reservations

        def crash(**kwargs):
            raise SystemExit("simulated crash before record_pending_transfer")

        store.record_pending_transfer = crash
        with self.assertRaises(SystemExit):
            service.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "x1")
            )

        # The reservation is orphaned: no pending transfer, no commit.
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.list_pending_transfers(), [])
        self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("0"))

        # Restart and reconcile. The orphan must be reclaimed, not left forever.
        # Age the row first: a real restart happens well after the grace period,
        # and a fresh reservation must never be reclaimed (see the other test).
        import sqlite3
        db = sqlite3.connect(self.db)
        db.execute(
            "UPDATE exposure_reservations SET created_at = created_at - 3600"
        )
        db.commit()
        db.close()

        restarted = self._service(cap="30")
        restarted.reconcile_exposure()
        self.assertEqual(
            restarted.reservations.count(), 0,
            "orphaned reservation still consumes capacity after reconcile",
        )

        # Capacity is usable again: three 10-notional entries fit a 30 cap.
        for index in (1, 2, 3):
            restarted.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), f"y{index}")
            )
        self.assertEqual(restarted.reservations.committed_for_symbol("EURUSD"), Decimal("30"))

    def test_live_reservation_is_not_reclaimed(self) -> None:
        """A reservation created moments ago must survive reconcile."""
        service = self._service(cap="30")
        service.reservations.reserve(
            "live-1", "EURUSD", Decimal("10"),
            ttl_seconds=None, max_symbol_notional=Decimal("30"),
        )
        service.reconcile_exposure()
        self.assertEqual(
            service.reservations.count(), 1,
            "a fresh in-flight reservation was wrongly reclaimed",
        )


if __name__ == "__main__":
    unittest.main()
