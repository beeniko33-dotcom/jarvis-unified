import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, RiskEngine, RiskLimits, ReservationError


class CorrelatedReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "reservations.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_reserve_release_and_expiry_fields(self):
        store = ExposureReservationStore(self.db)
        store.reserve("r1", "EURUSD", Decimal("10"), corr_group="fx_majors", ttl_seconds=60)
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("10"))
        self.assertEqual(store.reserved_for_group("fx_majors"), Decimal("10"))
        store.release("r1")
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("0"))
        with self.assertRaises(ReservationError):
            store.release("r1")

    def test_correlated_exposure_blocks_second_symbol(self):
        store = ExposureReservationStore(self.db)
        broker = PaperBroker(Decimal("10000"))
        risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("100"),
                max_daily_loss=Decimal("1000"),
                max_open_positions=10,
                kill_switch=False,
                correlation_groups={"fx": frozenset({"EURUSD", "GBPUSD"})},
                max_correlated_exposure=Decimal("15"),
            )
        )
        exec_svc = ExecutionService(broker, risk, reservations=store)
        exec_svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("10"), Decimal("1"), "a"))
        with self.assertRaises(PermissionError) as ctx:
            exec_svc.submit(OrderRequest("GBPUSD", Side.BUY, Decimal("10"), Decimal("1"), "b"))
        self.assertIn("correlated exposure", str(ctx.exception).lower())

    def test_cross_process_reservation_counts_toward_symbol_cap(self):
        store_a = ExposureReservationStore(self.db)
        store_b = ExposureReservationStore(self.db)
        store_a.reserve("other", "EURUSD", Decimal("8"), ttl_seconds=60)

        broker = PaperBroker(Decimal("10000"))
        risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("100"),
                max_daily_loss=Decimal("1000"),
                max_open_positions=10,
                kill_switch=False,
                max_symbol_exposure=Decimal("10"),
            )
        )
        exec_svc = ExecutionService(broker, risk, reservations=store_b)
        with self.assertRaises(PermissionError):
            exec_svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("3"), Decimal("1"), "x"))

    def test_concurrent_reservations_are_serialized(self):
        store = ExposureReservationStore(self.db)

        def work(i):
            rid = f"r-{i}"
            store.reserve(rid, "EURUSD", Decimal("1"), ttl_seconds=30)
            return rid

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(work, range(20)))
        self.assertEqual(len(set(ids)), 20)
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("20"))


if __name__ == "__main__":
    unittest.main()
