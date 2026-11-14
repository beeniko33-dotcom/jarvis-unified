"""Regression tests: committed exposure must not be double-counted against positions.

``ExecutionService.submit`` passes both the broker's live position notional
(``symbol_exposure``) and the reservation store's durable committed notional
(``committed_symbol``) to the risk gate, which adds them together. Both describe
the *same* filled exposure, so the sum is twice the real exposure and the
per-symbol cap trips at half its configured value.

The committed ledger exists so exposure survives a restart of the in-memory
broker; it is not additional exposure on top of a live position.
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


class ExposureDoubleCountTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = ExposureReservationStore(
            pathlib.Path(self._tmp.name) / "reservations.sqlite3"
        )

    def _service(self, *, cap: str, broker: PaperBroker | None = None) -> ExecutionService:
        broker = broker or PaperBroker(Decimal("1000"))
        risk = RiskEngine(
            RiskLimits(
                Decimal("50"),
                Decimal("100"),
                5,
                False,
                max_symbol_exposure=Decimal(cap),
            )
        )
        return ExecutionService(broker, risk, reservations=self.store)

    def test_symbol_cap_is_not_halved_by_committed_exposure(self) -> None:
        """Three 10-notional entries fit a 30 cap; the third must be allowed."""
        service = self._service(cap="30")
        for index in (1, 2, 3):
            service.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), f"o{index}")
            )
        position = service.broker.get_positions()[0]
        self.assertEqual(position.quantity, Decimal("3"))
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("30"))

    def test_symbol_cap_still_rejects_genuine_overflow(self) -> None:
        """The cap must still bite: a fourth 10-notional entry exceeds 30."""
        service = self._service(cap="30")
        for index in (1, 2, 3):
            service.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), f"o{index}")
            )
        with self.assertRaises(PermissionError):
            service.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "o4")
            )

    def test_committed_exposure_still_counts_after_broker_restart(self) -> None:
        """With an in-memory broker, committed rows are the only surviving record."""
        service = self._service(cap="30")
        service.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "r1")
        )
        service.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "r2")
        )
        # Simulate a restart: a fresh in-memory broker has no positions, but the
        # durable committed ledger still holds 20 of the 30 cap.
        restarted = self._service(cap="30", broker=PaperBroker(Decimal("1000")))
        restarted.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "r3")
        )
        with self.assertRaises(PermissionError):
            restarted.submit(
                OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "r4")
            )

    def test_correlated_group_cap_is_not_halved(self) -> None:
        """The same double-count must not halve a correlated-group cap."""
        broker = PaperBroker(Decimal("1000"))
        risk = RiskEngine(
            RiskLimits(
                Decimal("50"),
                Decimal("100"),
                5,
                False,
                correlation_groups={"EUR": frozenset({"EURUSD", "EURGBP"})},
                max_correlated_exposure=Decimal("30"),
            )
        )
        service = ExecutionService(broker, risk, reservations=self.store)
        service.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "g1")
        )
        service.submit(
            OrderRequest("EURGBP", Side.BUY, Decimal("1"), Decimal("10"), "g2")
        )
        service.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("10"), "g3")
        )
        self.assertEqual(self.store.committed_for_group("EUR"), Decimal("30"))


if __name__ == "__main__":
    unittest.main()
