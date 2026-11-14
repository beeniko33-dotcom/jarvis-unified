"""Repro: the 300-second grace period did not prove a submission was dead.

``_submission_lock`` is process-local, so a second process can reconcile while
a first process is still inside ``place_order()``. Reclaiming on age alone would
delete a live reservation and let a second order consume the same capacity.

The fix is a durable in-flight state: owner identity, a heartbeat and a lease.
A reservation is reclaimed only when its lease has expired *and* its owner is
confirmed dead. These tests exercise that with real separate processes.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from decimal import Decimal

from core.risk import ExposureReservationStore

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(code: str, db: pathlib.Path, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Run a snippet in a genuinely separate process against the same database."""
    script = textwrap.dedent(
        f"""
        import sys, time
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from decimal import Decimal
        from core.risk import ExposureReservationStore
        db = {str(db)!r}
        """
    ) + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


class ReservationLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = pathlib.Path(self._tmp.name) / "lease.sqlite3"

    def test_slow_in_flight_submission_survives_another_process_reconciling(self) -> None:
        """A live owner's reservation must not be reclaimed, however old it is."""
        # Process A: register as owner, take an in-flight reservation, then hold
        # it while heartbeating — exactly what a slow broker call does.
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(
                    f"""
                    import sys, time
                    sys.path.insert(0, {str(REPO_ROOT)!r})
                    from decimal import Decimal
                    from core.risk import ExposureReservationStore
                    store = ExposureReservationStore({str(self.db)!r})
                    store.register_owner("owner-A")
                    store.reserve(
                        "slow-1", "EURUSD", Decimal("10"),
                        ttl_seconds=None, max_symbol_notional=Decimal("30"),
                        owner_id="owner-A",
                    )
                    # Age the row far beyond any grace period, then keep the
                    # lease alive the way a real slow call would.
                    import sqlite3
                    db = sqlite3.connect({str(self.db)!r})
                    db.execute("UPDATE exposure_reservations SET created_at = created_at - 100000")
                    db.commit(); db.close()
                    for _ in range(40):
                        store.heartbeat("owner-A")
                        time.sleep(0.1)
                    """
                ),
            ],
            cwd=str(REPO_ROOT),
        )
        try:
            # Wait until the reservation exists and has been aged.
            deadline = time.time() + 30
            while time.time() < deadline:
                if self.db.exists():
                    store = ExposureReservationStore(self.db)
                    if store.count() == 1:
                        break
                time.sleep(0.1)
            else:
                self.fail("holder process never created its reservation")

            # Process B: reconcile while A is still in flight.
            other = ExposureReservationStore(self.db)
            reclaimed = other.reclaim_orphaned_reservations()
            self.assertEqual(
                reclaimed, [],
                "a live in-flight reservation was reclaimed by another process",
            )
            self.assertEqual(
                other.count(), 1,
                "a live in-flight reservation disappeared during reconcile",
            )
        finally:
            holder.wait(timeout=60)

    def test_dead_owner_reservation_is_reclaimed_after_lease_expiry(self) -> None:
        """A crashed owner's reservation is reclaimed once its lease lapses."""
        # A short-lived process takes an in-flight reservation and exits without
        # converting it — the crash-between-place_order-and-commit case.
        result = _run(
            """
store = ExposureReservationStore(db)
store.register_owner("owner-dead")
store.reserve(
    "orphan-1", "EURUSD", Decimal("10"),
    ttl_seconds=None, max_symbol_notional=Decimal("30"),
    owner_id="owner-dead",
)
print("reserved")
""",
            self.db,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reserved", result.stdout)

        store = ExposureReservationStore(self.db)
        self.assertEqual(store.count(), 1)

        # The owner process is gone, but its lease has not expired yet: the
        # reservation must survive, because a lease is the only cross-host
        # evidence and reclaiming early would be unsafe.
        self.assertEqual(
            store.reclaim_orphaned_reservations(), [],
            "reclaimed before the lease expired",
        )
        self.assertEqual(store.count(), 1)

        # Expire the lease. Now the owner is dead *and* the lease has lapsed.
        import sqlite3
        db = sqlite3.connect(self.db)
        db.execute("UPDATE exposure_reservations SET lease_expires_at = lease_expires_at - 10000")
        db.commit()
        db.close()

        reclaimed = store.reclaim_orphaned_reservations()
        self.assertEqual(reclaimed, ["orphan-1"])
        self.assertEqual(store.count(), 0)

    def test_live_owner_with_expired_lease_is_not_reclaimed(self) -> None:
        """Lease expiry alone is not enough: a live pid still protects the row."""
        store = ExposureReservationStore(self.db)
        store.register_owner("owner-live")
        store.reserve(
            "live-1", "EURUSD", Decimal("10"),
            ttl_seconds=None, max_symbol_notional=Decimal("30"),
            owner_id="owner-live",
        )
        import sqlite3
        db = sqlite3.connect(self.db)
        db.execute("UPDATE exposure_reservations SET lease_expires_at = lease_expires_at - 10000")
        db.commit()
        db.close()

        # This process is alive, so its own reservation must survive.
        self.assertEqual(
            store.reclaim_orphaned_reservations(), [],
            "reclaimed a reservation whose owner is still running",
        )
        self.assertEqual(store.count(), 1)

    def test_heartbeat_extends_the_lease(self) -> None:
        store = ExposureReservationStore(self.db)
        store.register_owner("owner-hb")
        store.reserve(
            "hb-1", "EURUSD", Decimal("10"),
            ttl_seconds=None, max_symbol_notional=Decimal("30"),
            owner_id="owner-hb",
        )
        import sqlite3
        db = sqlite3.connect(self.db)
        before = db.execute(
            "SELECT lease_expires_at FROM exposure_reservations WHERE reservation_id='hb-1'"
        ).fetchone()[0]
        db.close()

        store.heartbeat("owner-hb", now=time.time() + 30)

        db = sqlite3.connect(self.db)
        after = db.execute(
            "SELECT lease_expires_at FROM exposure_reservations WHERE reservation_id='hb-1'"
        ).fetchone()[0]
        db.close()
        self.assertGreater(after, before, "heartbeat did not extend the lease")

    def test_pending_transfer_is_never_reclaimed(self) -> None:
        """A reservation queued for conversion is not an orphan."""
        store = ExposureReservationStore(self.db)
        store.register_owner("owner-p")
        store.reserve(
            "p-1", "EURUSD", Decimal("10"),
            ttl_seconds=None, max_symbol_notional=Decimal("30"),
            owner_id="owner-p",
        )
        store.record_pending_transfer(
            reservation_id="p-1", order_id="o-1", client_order_id="c-1",
            symbol="EURUSD", notional=Decimal("10"), corr_group=None,
            error="pending conversion",
        )
        import sqlite3
        db = sqlite3.connect(self.db)
        db.execute("UPDATE exposure_reservations SET lease_expires_at = lease_expires_at - 10000")
        db.commit()
        db.close()

        self.assertEqual(store.reclaim_orphaned_reservations(), [])
        self.assertEqual(store.count(), 1)


if __name__ == "__main__":
    unittest.main()
