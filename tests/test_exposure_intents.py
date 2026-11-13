"""Write-ahead exposure intents: crash windows, duplicates, reductions, cross-service caps.

All state is synthetic paper state in temp directories. These tests use no market data,
broker, wallet, credential, or order endpoint and credit no Level 3 evidence.
"""
from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.execution import ExecutionService, PositionClosedReleaseFailedError
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, RiskEngine, RiskLimits


class _SimulatedCrash(BaseException):
    """Process death. BaseException so ``except Exception`` handlers cannot absorb it."""


def _order(symbol, side, qty, price, cid):
    return OrderRequest(symbol, side, D(qty), D(price), cid)


class IntentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def build(self, **limit_overrides):
        """Open broker + store + service on the same files, as a restarted process would."""
        limits = dict(
            max_stake_per_trade=D("1000"),
            max_daily_loss=D("100000"),
            max_open_positions=50,
            kill_switch=False,
        )
        limits.update(limit_overrides)
        broker = PersistentPaperBroker(D("1000000"), database_path=self.dir / "b.db")
        store = ExposureReservationStore(self.dir / "r.db")
        service = ExecutionService(broker, RiskEngine(RiskLimits(**limits)), reservations=store)
        return broker, store, service

    def assert_clean(self, store, *symbols):
        self.assertEqual(store.list_intents(), [], "no intent may outlive its operation")
        self.assertEqual(store.list_pending_transfers(), [])
        self.assertEqual(store.list_pending_releases(), [])
        for symbol in symbols:
            self.assertEqual(store.reserved_for_symbol(symbol), D("0"), f"reserved {symbol}")


class NormalFlowsLeaveNothingBehind(IntentTestCase):
    def test_open_reduce_close_cycle_clears_every_intent(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "4", "10", "o1"))
        self.assertEqual(store.committed_for_symbol("X"), D("40"))
        service.submit(_order("X", Side.SELL, "1", "10", "r1"))
        self.assertEqual(store.committed_for_symbol("X"), D("30"))
        service.close_position("X", D("10"))
        self.assertEqual(store.committed_for_symbol("X"), D("0"))
        self.assertEqual(broker.get_positions(), [])
        self.assert_clean(store, "X")

    def test_rejected_order_clears_its_intent(self):
        _, store, service = self.build(max_symbol_exposure=D("10"))
        with self.assertRaises(PermissionError):
            service.submit(_order("X", Side.BUY, "2", "10", "too-big"))
        self.assert_clean(store, "X")

    def test_broker_failure_after_reserve_releases_reservation_and_intent(self):
        broker, store, service = self.build()

        def refuse(order):
            raise ValueError("broker refused")

        broker.place_order = refuse
        with self.assertRaises(ValueError):
            service.submit(_order("X", Side.BUY, "1", "10", "b1"))
        self.assert_clean(store, "X")


class PartialReductionAndReversal(IntentTestCase):
    def test_partial_reduction_releases_proportional_committed_exposure(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "4", "10", "o1"))
        service.submit(_order("X", Side.SELL, "1", "10", "r1"))
        self.assertEqual(broker.get_positions()[0].quantity, D("3"))
        self.assertEqual(store.committed_for_symbol("X"), D("30"))
        service.submit(_order("X", Side.SELL, "3", "10", "r2"))
        self.assertEqual(broker.get_positions(), [])
        self.assertEqual(store.committed_for_symbol("X"), D("0"))

    def test_reversal_in_one_order_is_rejected_with_no_side_effects(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "10", "o1"))
        with self.assertRaisesRegex(PermissionError, "reverse"):
            service.submit(_order("X", Side.SELL, "2", "10", "flip"))
        self.assertEqual(broker.get_positions()[0].quantity, D("1"))
        self.assertEqual(store.committed_for_symbol("X"), D("10"))
        self.assert_clean(store, "X")

    def test_reducing_order_is_not_blocked_by_exposure_or_position_caps(self):
        broker, store, service = self.build(max_symbol_exposure=D("10"), max_open_positions=1)
        service.submit(_order("X", Side.BUY, "1", "10", "o1"))  # exactly at both caps
        service.submit(_order("X", Side.SELL, "1", "10", "r1"))  # must still be allowed
        self.assertEqual(broker.get_positions(), [])
        self.assertEqual(store.committed_for_symbol("X"), D("0"))

    def test_reducing_order_still_respects_the_kill_switch(self):
        _, _, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "10", "o1"))
        service.risk.engage_kill_switch()
        with self.assertRaises(PermissionError):
            service.submit(_order("X", Side.SELL, "1", "10", "r1"))
        # close_position remains the always-available safety path.
        service.close_position("X", D("10"))


class CrashWindows(IntentTestCase):
    def test_crash_between_reserve_and_broker_call_is_released_only_when_stale(self):
        _, store, service = self.build()

        def die(order):
            raise _SimulatedCrash()

        service.broker.place_order = die
        with self.assertRaises(_SimulatedCrash):
            service.submit(_order("X", Side.BUY, "1", "10", "c1"))

        broker2, store2, service2 = self.build()
        self.assertEqual(store2.reserved_for_symbol("X"), D("10"))
        self.assertEqual(len(service2.in_flight_intents), 1)

        # Default stale window protects a submission that may still be in flight.
        service2.reconcile_exposure()
        self.assertEqual(store2.reserved_for_symbol("X"), D("10"))

        fixed = service2.reconcile_exposure(stale_after_seconds=0)
        self.assertEqual([item["action"] for item in fixed], ["released_unexecuted"])
        self.assertEqual(broker2.get_positions(), [])
        self.assert_clean(store2, "X")
        # The released capacity is usable again.
        service2.submit(_order("X", Side.BUY, "1", "10", "c2"))

    def test_crash_after_fill_is_settled_immediately_regardless_of_age(self):
        _, store, service = self.build()

        def die(**_kwargs):
            raise _SimulatedCrash()

        store.record_pending_transfer = die
        with self.assertRaises(_SimulatedCrash):
            service.submit(_order("X", Side.BUY, "1", "10", "c1"))

        broker2, store2, service2 = self.build()
        fixed = service2.reconcile_exposure()  # default stale window: fill is real, so settle
        self.assertEqual([item["action"] for item in fixed], ["settled_fill"])
        self.assertEqual(store2.committed_for_symbol("X"), D("10"))
        self.assertEqual(len(broker2.get_positions()), 1)
        self.assert_clean(store2, "X")
        # Recovery is idempotent.
        self.assertEqual(service2.reconcile_exposure(), [])

    def test_crash_before_broker_close_keeps_exposure_and_discards_stale_intent(self):
        _, store, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "10", "o1"))

        def die(*_args, **_kwargs):
            raise _SimulatedCrash()

        service.broker.close_position = die
        with self.assertRaises(_SimulatedCrash):
            service.close_position("X", D("10"))

        broker2, store2, service2 = self.build()
        service2.reconcile_exposure(stale_after_seconds=0)
        # The position never closed, so its exposure must NOT be released.
        self.assertEqual(len(broker2.get_positions()), 1)
        self.assertEqual(store2.committed_for_symbol("X"), D("10"))
        self.assertEqual(store2.list_intents(), [])

    def test_crash_after_reduce_fill_before_release_is_recovered(self):
        _, store, service = self.build()
        service.submit(_order("X", Side.BUY, "2", "10", "o1"))

        def die(*_args, **_kwargs):
            raise _SimulatedCrash()

        store.reduce_committed_for_position = die
        with self.assertRaises(_SimulatedCrash):
            service.submit(_order("X", Side.SELL, "1", "10", "r1"))

        broker2, store2, service2 = self.build()
        self.assertEqual(store2.committed_for_symbol("X"), D("20"))  # still stranded
        fixed = service2.reconcile_exposure()
        self.assertEqual([item["action"] for item in fixed], ["settled_fill"])
        self.assertEqual(broker2.get_positions()[0].quantity, D("1"))
        self.assertEqual(store2.committed_for_symbol("X"), D("10"))
        self.assert_clean(store2, "X")

    def test_intent_write_failure_never_blocks_a_close(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "10", "o1"))

        def fail(*_args, **_kwargs):
            raise RuntimeError("exposure db hiccup")

        store.record_intent = fail
        service.close_position("X", D("10"))  # safety action proceeds
        self.assertEqual(broker.get_positions(), [])
        self.assertEqual(store.committed_for_symbol("X"), D("0"))
        self.assertTrue(
            any(f.get("phase") == "intent_record_failed" for f in service.release_failures)
        )

    def test_failed_release_after_reduction_is_typed_and_queued(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "2", "10", "o1"))
        with store._lock, store._connect() as db:
            db.execute("DELETE FROM exposure_committed")
        with self.assertRaises(PositionClosedReleaseFailedError):
            service.submit(_order("X", Side.SELL, "1", "10", "r1"))
        self.assertEqual(broker.get_positions()[0].quantity, D("1"))
        self.assertEqual(len(store.list_pending_releases()), 1)
        self.assertEqual(store.list_intents(), [], "pending release must own it exclusively")


class DuplicatesAndRestarts(IntentTestCase):
    def test_duplicate_after_restart_returns_same_order_without_reserving(self):
        _, store, service = self.build()
        first = service.submit(_order("X", Side.BUY, "1", "10", "dup"))
        _, store2, service2 = self.build()
        again = service2.submit(_order("X", Side.BUY, "1", "10", "dup"))
        self.assertEqual(first.order_id, again.order_id)
        self.assertEqual(store2.committed_for_symbol("X"), D("10"))
        self.assert_clean(store2, "X")

    def test_same_client_id_with_different_payload_is_rejected_cleanly(self):
        broker, store, service = self.build()
        service.submit(_order("X", Side.BUY, "1", "10", "dup"))
        with self.assertRaises(ValueError):
            service.submit(_order("X", Side.BUY, "2", "10", "dup"))
        self.assertEqual(broker.get_positions()[0].quantity, D("1"))
        self.assert_clean(store, "X")

    def test_concurrent_duplicates_across_services_fill_exactly_once(self):
        services = [self.build()[2] for _ in range(4)]
        order = _order("X", Side.BUY, "1", "10", "same")

        def attempt(index):
            try:
                return services[index % 4].submit(order).order_id
            except PermissionError:
                return None  # in-flight duplicate refused: acceptable

        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(attempt, range(24)))
        ids = {o for o in outcomes if o is not None}
        self.assertEqual(len(ids), 1, "exactly one distinct fill")
        broker, store, service = self.build()
        service.reconcile_exposure(stale_after_seconds=0)
        self.assertEqual(len(broker.get_positions()), 1)
        self.assertEqual(store.committed_for_symbol("X"), D("10"))
        self.assert_clean(store, "X")

    def test_retry_while_pending_conversion_does_not_double_reserve(self):
        _, store, service = self.build()

        def fail(*_args, **_kwargs):
            raise RuntimeError("simulated commit failure")

        store.commit_exposure = fail
        with self.assertRaises(Exception):
            service.submit(_order("X", Side.BUY, "1", "10", "q1"))
        _, store2, service2 = self.build()
        service2.submit(_order("X", Side.BUY, "1", "10", "q1"))  # client retries first
        self.assertEqual(store2.reserved_for_symbol("X"), D("10"), "only the original")
        service2.reconcile_exposure()
        self.assertEqual(store2.committed_for_symbol("X"), D("10"))
        self.assert_clean(store2, "X")

    def test_cancelled_zero_fill_client_id_can_be_reused_after_restart(self):
        broker = PersistentPaperBroker(D("1000"), database_path=self.dir / "p.db")
        working = broker.place_working_order(_order("N", Side.BUY, "1", "10", "n1"))
        broker.cancel_order(working.order_id)
        restarted = PersistentPaperBroker(D("1000"), database_path=self.dir / "p.db")
        result = restarted.place_order(_order("N", Side.BUY, "1", "10", "n1"))
        self.assertEqual(result.status, "filled")

    def test_broker_lookup_sees_fills_made_by_another_instance(self):
        a = PersistentPaperBroker(D("1000"), database_path=self.dir / "p.db")
        b = PersistentPaperBroker(D("1000"), database_path=self.dir / "p.db")
        self.assertIsNone(b.get_order_by_client_id("z1"))
        filled = a.place_order(_order("Z", Side.BUY, "1", "10", "z1"))
        seen = b.get_order_by_client_id("z1")
        self.assertIsNotNone(seen)
        self.assertEqual(seen.order_id, filled.order_id)


class ExposureLimits(IntentTestCase):
    def test_exposure_exactly_at_the_limit_is_allowed_then_one_more_is_not(self):
        _, _, service = self.build(max_symbol_exposure=D("10"))
        service.submit(_order("X", Side.BUY, "1", "5", "a1"))
        service.submit(_order("X", Side.BUY, "1", "5", "a2"))
        with self.assertRaises(PermissionError):
            service.submit(_order("X", Side.BUY, "1", "1", "a3"))

    def test_open_position_cap_holds_across_concurrent_services(self):
        services = [self.build(max_open_positions=2)[2] for _ in range(4)]

        def attempt(index):
            try:
                services[index % 4].submit(_order(f"S{index}", Side.BUY, "1", "10", f"c{index}"))
                return True
            except PermissionError:
                return False

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(attempt, range(16)))
        broker, store, _ = self.build()
        self.assertEqual(len(broker.get_positions()), 2)
        self.assertEqual(results.count(True), 2)
        self.assertEqual(store.list_pending_transfers(), [])


if __name__ == "__main__":
    unittest.main()
