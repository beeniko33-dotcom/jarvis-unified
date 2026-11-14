"""Reproduction tests for exposure-release defects found reviewing PR #22.

These are written to FAIL against head f3a36aa and pass after the fix.

Finding 1 - pending release ignores its recorded notional.
    close_position() records a pending release with the notional it intended to
    release, but reconcile_exposure() retries without passing that notional.
    reduce_committed_for_position() then treats notional=None as "release
    everything", so a retried partial release consumes the whole commitment.

Finding 2 - reconciled transfers lose their position link.
    submit() tags commits with position_id, but reconcile_exposure() re-commits
    a pending transfer without position_id, so a crash-recovered entry becomes a
    legacy symbol-wide commit and can no longer be released by position.
"""
from contextlib import closing
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, RiskEngine, RiskLimits


def _risk(**overrides):
    limits = dict(
        max_stake_per_trade=Decimal("1000"),
        max_daily_loss=Decimal("10000"),
        max_open_positions=10,
        kill_switch=False,
    )
    limits.update(overrides)
    engine = RiskEngine(RiskLimits(**limits))
    engine.release_kill_switch(explicit_operator_action=True)
    return engine


class PendingReleaseNotionalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ExposureReservationStore(Path(self.tmp.name) / "exposure.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_retried_pending_release_honours_its_recorded_notional(self):
        """A queued partial release must release only what it recorded."""
        self.store.commit_exposure(
            "entry-1", "EURUSD", Decimal("10"), position_id="EURUSD"
        )
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("10"))

        # Queue a release of 4 of the 10 committed, as a partial close would.
        self.store.record_pending_release(
            "exit-1", "EURUSD", Decimal("4"), "simulated db retry",
            position_id="EURUSD",
        )

        service = ExecutionService(
            PaperBroker(Decimal("10000")), _risk(), reservations=self.store
        )
        reconciled = service.reconcile_exposure()
        self.assertEqual(len(reconciled), 1)

        remaining = self.store.committed_for_symbol("EURUSD")
        self.assertEqual(
            remaining,
            Decimal("6"),
            f"retried release of 4 should leave 6 committed, got {remaining}",
        )

    def test_retried_pending_release_is_idempotent(self):
        self.store.commit_exposure(
            "entry-2", "EURUSD", Decimal("10"), position_id="EURUSD"
        )
        self.store.record_pending_release(
            "exit-2", "EURUSD", Decimal("4"), "simulated db retry",
            position_id="EURUSD",
        )
        service = ExecutionService(
            PaperBroker(Decimal("10000")), _risk(), reservations=self.store
        )
        service.reconcile_exposure()
        service.reconcile_exposure()
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("6"))


class ReconciledTransferPositionLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ExposureReservationStore(Path(self.tmp.name) / "exposure.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconciled_transfer_keeps_its_position_link(self):
        """A crash-recovered entry commit must stay releasable by position."""
        self.store.reserve("res-1", "EURUSD", Decimal("10"), ttl_seconds=None)
        self.store.record_pending_transfer(
            reservation_id="res-1",
            order_id="order-1",
            client_order_id="client-1",
            symbol="EURUSD",
            notional=Decimal("10"),
            corr_group=None,
            error="pending conversion",
        )

        service = ExecutionService(
            PaperBroker(Decimal("10000")), _risk(), reservations=self.store
        )
        service.reconcile_exposure()
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("10"))

        # The recovered commit must be position-linked, not a legacy row.
        with self.store._lock, closing(self.store._connect()) as db:
            rows = db.execute(
                "SELECT position_id FROM exposure_committed WHERE commit_id=?",
                ("order-1",),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(
            rows[0][0],
            "reconciled commit lost its position_id and became symbol-wide",
        )


if __name__ == "__main__":
    unittest.main()
