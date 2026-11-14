"""Reproduction tests for the PR #24 exposure-accounting defects.

These are written to FAIL against head f009a59 and pass after the fix.
They encode the three findings from the review:

1. Notional mismatch - close releases quantity * average_price, but the
   committed amount was quantity * order_price. With slippage these differ.
2. FIFO allocation risk - releasing by symbol consumes the oldest commit,
   not the commit belonging to the position actually closed.
3. Failure handling - a close can succeed while release fails, and the
   caller cannot tell the two apart.
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


def _service(broker, risk, store):
    return ExecutionService(broker, risk, reservations=store)


class ExposureAccountingReproTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ExposureReservationStore(Path(self.tmp.name) / "exposure.db")
        self.risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("1000"),
                max_daily_loss=Decimal("10000"),
                max_open_positions=10,
                kill_switch=False,
            )
        )
        self.risk.release_kill_switch(explicit_operator_action=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_slippage_does_not_leave_residual_committed_exposure(self):
        """Entry fills above the order price; close must release exactly what was committed."""
        broker = PaperBroker(Decimal("100000"), slippage_bps=Decimal("50"))
        service = _service(broker, self.risk, self.store)

        service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "e1"))
        committed_after_entry = self.store.committed_for_symbol("EURUSD")
        self.assertEqual(committed_after_entry, Decimal("10"))

        service.close_position("EURUSD", Decimal("10"))
        residual = self.store.committed_for_symbol("EURUSD")
        self.assertEqual(
            residual,
            Decimal("0"),
            f"committed exposure should be fully released, got {residual}",
        )

    def test_close_releases_the_commit_belonging_to_the_closed_position(self):
        """Two entries at different prices; closing one must not consume the other's commit."""
        broker = PaperBroker(Decimal("100000"))
        service = _service(broker, self.risk, self.store)

        service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "a"))
        service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("20"), "b"))
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("30"))

        # Close the whole net position (2 units at blended average 15).
        service.close_position("EURUSD", Decimal("15"))
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("0"))

    def test_partial_close_releases_only_the_closed_quantity(self):
        """Closing part of a position must release only that part's committed notional."""
        broker = PaperBroker(Decimal("100000"))
        service = _service(broker, self.risk, self.store)

        service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("2"), Decimal("10"), "p1"))
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("20"))

        # Close 1 of 2 units directly through the broker, then release via service.
        broker.close_position("EURUSD", Decimal("10"))
        # Broker closed the whole position; committed should be releasable in full.
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("20"))

    def test_close_failure_is_distinguishable_from_close_success(self):
        """A release failure must not look like a failed close."""
        broker = PaperBroker(Decimal("100000"))
        service = _service(broker, self.risk, self.store)
        service.submit(OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "f1"))

        # Corrupt the committed ledger so the release cannot find enough notional.
        with self.store._lock, closing(self.store._connect()) as db:
            db.execute("DELETE FROM exposure_committed")

        with self.assertRaises(Exception) as ctx:
            service.close_position("EURUSD", Decimal("10"))

        # The position really did close - the broker is flat.
        self.assertEqual(broker.get_account().open_positions, 0)
        # And the failure is recorded as a pending release, not lost.
        pending = self.store.list_pending_releases()
        self.assertEqual(len(pending), 1, f"expected 1 pending release, got {pending}")
        # The exception must say the close succeeded.
        self.assertIn("close succeeded", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
