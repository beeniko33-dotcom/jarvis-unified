"""Regression tests for review findings 12.x and 17.x (paper-only)."""
from __future__ import annotations

import multiprocessing as mp
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from brokers.paper import PaperBroker, PersistentPaperBroker
from core.execution import ExecutionService, ReconciliationRequiredError
from core.models import OrderRequest, Side
from core.risk import ExposureReservationStore, ReservationError, RiskEngine, RiskLimits


def _mp_submit(args):
    db_path, index = args
    store = ExposureReservationStore(db_path)
    risk = RiskEngine(
        RiskLimits(
            max_stake_per_trade=Decimal("100"),
            max_daily_loss=Decimal("1000"),
            max_open_positions=10,
            kill_switch=False,
            max_symbol_exposure=Decimal("10"),
        )
    )
    broker = PaperBroker(Decimal("10000"))
    svc = ExecutionService(broker, risk, reservations=store)
    try:
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("6"), Decimal("1"), f"mp-{index}"))
        return "ok"
    except PermissionError:
        return "blocked"


def _subprocess_leave_pending(db_path: str) -> None:
    """Child process: fill + failed commit, exit without reconciling."""
    store = ExposureReservationStore(db_path)
    risk = RiskEngine(
        RiskLimits(
            max_stake_per_trade=Decimal("100"),
            max_daily_loss=Decimal("1000"),
            max_open_positions=10,
            kill_switch=False,
            max_symbol_exposure=Decimal("20"),
        )
    )
    broker = PaperBroker(Decimal("10000"))
    svc = ExecutionService(broker, risk, reservations=store)

    real_commit = store.commit_exposure

    def fail_commit(*args, **kwargs):
        raise RuntimeError("subprocess simulated commit failure")

    store.commit_exposure = fail_commit  # type: ignore[method-assign]
    try:
        svc.submit(OrderRequest("EURUSD", Side.BUY, Decimal("4"), Decimal("1"), "sub-1"))
    except ReconciliationRequiredError:
        return
    finally:
        store.commit_exposure = real_commit  # type: ignore[method-assign]
    raise AssertionError("expected ReconciliationRequiredError")


class AtomicReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "res.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_wal_setup_retries_transient_database_lock(self):
        connection = mock.Mock()
        connection.execute.side_effect = [
            sqlite3.OperationalError("database is locked"),
            None,
        ]

        with mock.patch("core.risk.reservations.time.sleep") as sleep:
            ExposureReservationStore._enable_wal(connection)

        self.assertEqual(connection.execute.call_count, 2)
        sleep.assert_called_once_with(0.01)

    def test_atomic_capacity_rejects_over_limit_under_contention(self):
        store = ExposureReservationStore(self.db)
        errors = []
        successes = []

        def try_reserve(i):
            rid = f"r-{i}"
            try:
                store.reserve(
                    rid,
                    "EURUSD",
                    Decimal("6"),
                    max_symbol_notional=Decimal("10"),
                    existing_symbol_exposure=Decimal("0"),
                    ttl_seconds=60,
                )
                successes.append(rid)
            except ReservationError as exc:
                errors.append(str(exc))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(try_reserve, range(12)))

        self.assertEqual(len(successes), 1)
        self.assertGreaterEqual(len(errors), 11)
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("6"))

    def test_committed_exposure_survives_reservation_release(self):
        store = ExposureReservationStore(self.db)
        store.reserve("tmp", "EURUSD", Decimal("6"), max_symbol_notional=Decimal("10"))
        store.commit_exposure("order-1", "EURUSD", Decimal("6"), reservation_id="tmp")
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("0"))
        self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("6"))
        with self.assertRaises(ReservationError):
            store.reserve(
                "tmp2",
                "EURUSD",
                Decimal("5"),
                max_symbol_notional=Decimal("10"),
                existing_symbol_exposure=Decimal("0"),
            )

    def test_multiprocess_symbol_cap(self):
        with mp.get_context("spawn").Pool(processes=4) as pool:
            results = pool.map(_mp_submit, [(str(self.db), i) for i in range(6)])
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("blocked"), 5)
        store = ExposureReservationStore(self.db)
        self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("6"))

    def test_commit_failure_retains_reservation_and_reconciles(self):
        store = ExposureReservationStore(self.db)
        risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("100"),
                max_daily_loss=Decimal("1000"),
                max_open_positions=10,
                kill_switch=False,
                max_symbol_exposure=Decimal("20"),
            )
        )
        broker = PaperBroker(Decimal("10000"))
        svc = ExecutionService(broker, risk, reservations=store)

        real_commit = store.commit_exposure
        calls = {"n": 0}

        def flaky_commit(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated commit failure")
            return real_commit(*args, **kwargs)

        with mock.patch.object(store, "commit_exposure", side_effect=flaky_commit):
            with self.assertRaises(ReconciliationRequiredError):
                svc.submit(
                    OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("1"), "recon-1")
                )
            self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("5"))
            self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("0"))
            self.assertEqual(len(svc.pending_reconciliation), 1)

        fixed = svc.reconcile_exposure()
        self.assertEqual(len(fixed), 1)
        self.assertEqual(store.reserved_for_symbol("EURUSD"), Decimal("0"))
        self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("5"))
        self.assertEqual(svc.pending_reconciliation, [])

    def test_subprocess_restart_reconciles_pending_once(self):
        """Genuine OS child process leaves pending; parent recovers against same DB."""
        ctx = mp.get_context("spawn")
        child = ctx.Process(target=_subprocess_leave_pending, args=(str(self.db),))
        child.start()
        child.join(timeout=30)
        self.assertEqual(child.exitcode, 0)

        recovered_store = ExposureReservationStore(self.db)
        self.assertEqual(recovered_store.reserved_for_symbol("EURUSD"), Decimal("4"))
        self.assertEqual(recovered_store.committed_for_symbol("EURUSD"), Decimal("0"))
        pending = recovered_store.list_pending_transfers()
        self.assertEqual(len(pending), 1)
        self.assertEqual(Decimal(pending[0]["notional"]), Decimal("4"))

        risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("100"),
                max_daily_loss=Decimal("1000"),
                max_open_positions=10,
                kill_switch=False,
                max_symbol_exposure=Decimal("20"),
            )
        )
        recovered_svc = ExecutionService(
            PaperBroker(Decimal("10000")),
            risk,
            reservations=recovered_store,
        )
        fixed = recovered_svc.reconcile_exposure()
        self.assertEqual(len(fixed), 1)
        self.assertEqual(recovered_store.reserved_for_symbol("EURUSD"), Decimal("0"))
        self.assertEqual(recovered_store.committed_for_symbol("EURUSD"), Decimal("4"))
        self.assertEqual(recovered_store.list_pending_transfers(), [])
        self.assertEqual(recovered_svc.reconcile_exposure(), [])


class CloseExposureReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "res.sqlite3"
        self.store = ExposureReservationStore(self.db)
        self.broker = PaperBroker(Decimal("10000"))
        self.risk = RiskEngine(RiskLimits(
            max_stake_per_trade=Decimal("100"), max_daily_loss=Decimal("1000"),
            max_open_positions=10, kill_switch=False,
            max_symbol_exposure=Decimal("20"),
        ))
        self.service = ExecutionService(self.broker, self.risk, reservations=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_close_releases_committed_exposure_and_is_idempotent(self):
        opened = self.service.submit(
            OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("2"), "open-1")
        )
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("10"))
        closed = self.service.close_position("eurusd", Decimal("3"))
        self.assertNotEqual(opened.order_id, closed.order_id)
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("0"))
        self.store.reduce_committed_for_symbol(
            closed.order_id, "EURUSD", Decimal("10")
        )
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("0"))

    def test_partial_release_preserves_remaining_committed_exposure(self):
        self.store.commit_exposure("entry-1", "EURUSD", Decimal("10"))
        self.store.reduce_committed_for_symbol("exit-1", "EURUSD", Decimal("4"))
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("6"))


    def test_pending_close_release_reconciles_after_restart(self):
        self.store.commit_exposure("entry-2", "EURUSD", Decimal("8"))
        self.store.record_pending_release("exit-2", "EURUSD", Decimal("8"), "simulated db retry")
        self.assertEqual(len(self.store.list_pending_releases()), 1)
        fixed = self.service.reconcile_exposure()
        self.assertEqual(len(fixed), 1)
        self.assertEqual(self.store.committed_for_symbol("EURUSD"), Decimal("0"))
        self.assertEqual(self.store.list_pending_releases(), [])


class FillIdempotencyTests(unittest.TestCase):
    def test_duplicate_fill_id_does_not_double_apply(self):
        broker = PaperBroker(Decimal("1000"))
        opened = broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("1"), "w")
        )
        first = broker.apply_partial_fill(
            opened.order_id, Decimal("2"), fill_id="fill-1"
        )
        second = broker.apply_partial_fill(
            opened.order_id, Decimal("2"), fill_id="fill-1"
        )
        self.assertEqual(first.filled_quantity, second.filled_quantity)
        self.assertEqual(broker.get_positions()[0].quantity, Decimal("2"))

    def test_fill_id_cannot_be_reused_across_orders(self):
        broker = PaperBroker(Decimal("1000"))
        a = broker.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("1"), "a")
        )
        b = broker.place_working_order(
            OrderRequest("GBPUSD", Side.BUY, Decimal("5"), Decimal("1"), "b")
        )
        broker.apply_partial_fill(a.order_id, Decimal("1"), fill_id="shared")
        with self.assertRaises(ValueError):
            broker.apply_partial_fill(b.order_id, Decimal("1"), fill_id="shared")

    def test_duplicate_fill_id_survives_persistent_restart(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "paper.sqlite3"
        now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

        first = PersistentPaperBroker(Decimal("1000"), database_path=db, clock=lambda: now)
        opened = first.place_working_order(
            OrderRequest("EURUSD", Side.BUY, Decimal("5"), Decimal("1"), "w")
        )
        first.apply_partial_fill(opened.order_id, Decimal("2"), fill_id="fill-1")

        recovered = PersistentPaperBroker(Decimal("1000"), database_path=db, clock=lambda: now)
        recovered.apply_partial_fill(opened.order_id, Decimal("2"), fill_id="fill-1")
        self.assertEqual(recovered.get_positions()[0].quantity, Decimal("2"))


class ExecutionCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "res.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_executors_cannot_exceed_symbol_cap(self):
        store = ExposureReservationStore(self.db)
        risk = RiskEngine(
            RiskLimits(
                max_stake_per_trade=Decimal("100"),
                max_daily_loss=Decimal("1000"),
                max_open_positions=10,
                kill_switch=False,
                max_symbol_exposure=Decimal("10"),
            )
        )

        def attempt(i):
            broker = PaperBroker(Decimal("10000"))
            svc = ExecutionService(broker, risk, reservations=store)
            try:
                svc.submit(
                    OrderRequest("EURUSD", Side.BUY, Decimal("6"), Decimal("1"), f"c{i}")
                )
                return "ok"
            except PermissionError:
                return "blocked"

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(attempt, i) for i in range(6)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("blocked"), 5)
        self.assertEqual(store.committed_for_symbol("EURUSD"), Decimal("6"))


if __name__ == "__main__":
    unittest.main()
