"""The only supported path from strategy orders to a broker adapter.

Exposure accounting protocol (paper-only)
-----------------------------------------
The broker and the exposure store are separate databases, so no single transaction spans
"the order filled" and "the exposure was recorded". Instead every mutation is preceded by
a durable *intent* and every crash window is resolved by asking the broker what really
happened:

* **open**   - ``reserve()`` writes the reservation and an 'open' intent keyed by the
  client order ID in one transaction, *before* the broker is called. After the fill the
  reservation is converted to committed exposure (clearing the intent atomically).
* **reduce** - a risk-reducing order records a 'reduce' intent first; the release of the
  committed exposure clears it atomically.
* **close**  - ``close_position()`` chooses the closing order's client ID up front and records
  a 'close' intent under it, so recovery can look the exact order up at the broker.

``reconcile_exposure()`` resolves whatever a crash left behind: an intent whose order
filled is settled; an intent whose order never reached the broker is released once it is
older than ``stale_intent_seconds`` (so an in-flight submission is never torn down).

What is atomic, and what is not
-------------------------------
Atomic across every service or process that shares one reservation store: the per-symbol
and correlated notional caps, the open-symbol cap, and refusal of a second in-flight
submission of the same client order ID. All three are enforced inside the store's own
transaction.

Not atomic (evaluated against a snapshot taken just before the order): the daily-loss,
drawdown and quote-freshness gates, and the position quantity used to decide that an order
is risk-reducing. Concurrent writers can overshoot those by the size of the orders in
flight. Run one execution service per broker database to enforce them strictly.

The runner must call ``reconcile_exposure()`` at startup and periodically; nothing resolves
a crash's leftovers on its own.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from brokers.base import Broker
from core.models import AccountSnapshot, OrderRequest, OrderResult, OrderStatus, Position, Side
from core.risk import ExposureReservationStore, ReservationError, RiskEngine

logger = logging.getLogger(__name__)

DEFAULT_STALE_INTENT_SECONDS = 60.0


class ReconciliationRequiredError(RuntimeError):
    """Paper fill succeeded but durable exposure commit did not.

    A pending transfer is written to SQLite *before* conversion is attempted, so
    a restarted process can call reconcile_exposure() even if the first process
    died mid-conversion. The temporary reservation is retained until conversion.
    """

    def __init__(
        self,
        message: str,
        *,
        order_result: OrderResult,
        reservation_id: str,
        symbol: str,
        notional: Decimal,
        corr_group: str | None,
    ) -> None:
        super().__init__(message)
        self.order_result = order_result
        self.reservation_id = reservation_id
        self.symbol = symbol
        self.notional = notional
        self.corr_group = corr_group


class PositionClosedReleaseFailedError(RuntimeError):
    """The paper position closed successfully, but its exposure release did not.

    Callers must treat this as *close succeeded, accounting pending* — not as a
    failed close. The position is flat at the broker; the release is persisted
    in ``exposure_pending_releases`` and retried by ``reconcile_exposure()``.
    """

    def __init__(
        self,
        message: str,
        *,
        order_result: OrderResult,
        symbol: str,
        position_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.order_result = order_result
        self.symbol = symbol
        self.position_id = position_id


class ExecutionService:
    def __init__(
        self,
        broker: Broker,
        risk: RiskEngine,
        *,
        reservations: ExposureReservationStore | None = None,
        stale_intent_seconds: float = DEFAULT_STALE_INTENT_SECONDS,
    ) -> None:
        if stale_intent_seconds < 0:
            raise ValueError("stale_intent_seconds must be non-negative")
        self.broker = broker
        self.risk = risk
        self.reservations = reservations
        self.stale_intent_seconds = float(stale_intent_seconds)
        self._submission_lock = RLock()
        self._release_failures: list[dict] = []

    # ------------------------------------------------------------------ properties
    @property
    def release_failures(self) -> list[dict]:
        with self._submission_lock:
            return list(self._release_failures)

    @property
    def pending_reconciliation(self) -> list[dict]:
        if self.reservations is None:
            return []
        return self.reservations.list_pending_transfers()

    @property
    def in_flight_intents(self) -> list[dict]:
        """Durable intents not yet resolved; non-empty after a crash until reconciled."""
        if self.reservations is None:
            return []
        return self.reservations.list_intents()

    # ------------------------------------------------------------------ helpers
    @property
    def _can_lookup(self) -> bool:
        return callable(getattr(self.broker, "get_order_by_client_id", None))

    def _lookup_order(self, client_order_id: str) -> OrderResult | None:
        lookup = getattr(self.broker, "get_order_by_client_id", None)
        return None if lookup is None else lookup(client_order_id)

    @staticmethod
    def _pnl_inputs(account: AccountSnapshot) -> dict:
        return {
            "daily_realized_pnl": (
                account.daily_realized_pnl
                if account.daily_accounting_available
                else account.realized_pnl
            ),
            "unrealized_pnl": account.equity - account.balance,
            "commission_paid": (
                account.daily_commission_paid
                if account.daily_accounting_available
                else account.commission_paid
            ),
            "current_equity": account.equity,
            "peak_equity": account.peak_equity,
        }

    @staticmethod
    def _reduces(position: Position, order: OrderRequest) -> bool:
        signed = Decimal("1") if order.side == Side.BUY else Decimal("-1")
        return position.quantity * signed < 0

    def _record_failure(self, **details: object) -> None:
        self._release_failures.append(dict(details))

    def _discard_intent(self, client_order_id: str) -> None:
        if self.reservations is None:
            return
        try:
            self.reservations.discard_intent(client_order_id)
        except Exception as exc:  # recovery will resolve it once it goes stale
            self._record_failure(
                client_order_id=client_order_id, error=str(exc), phase="discard_intent_failed"
            )
            logger.warning("intent discard failed id=%s error=%s", client_order_id, exc)

    def _record_safety_intent(
        self, client_order_id: str, kind: str, symbol: str, notional: Decimal | None
    ) -> bool:
        """Record a reduce/close intent. Never blocks a risk-reducing action.

        Closing a position is a safety action; an exposure-database hiccup must not
        prevent it. If the intent cannot be written the action proceeds and the
        (typed) post-close release failure path still captures the accounting.
        """
        assert self.reservations is not None
        try:
            self.reservations.record_intent(
                client_order_id, kind, symbol, position_id=symbol, notional=notional
            )
            return True
        except Exception as exc:
            self._record_failure(
                client_order_id=client_order_id, symbol=symbol, error=str(exc),
                phase="intent_record_failed",
            )
            logger.warning(
                "could not record %s intent id=%s symbol=%s error=%s; proceeding",
                kind, client_order_id, symbol, exc,
            )
            return False

    # ------------------------------------------------------------------ submit
    def submit(self, order: OrderRequest) -> OrderResult:
        with self._submission_lock:
            symbol = order.symbol.strip().upper()

            # An order that already executed is an idempotent lookup, never a second
            # execution and never a second reservation. The broker still validates that
            # the retry carries the same request.
            prior = self._lookup_order(order.client_order_id)
            if prior is not None:
                result = self.broker.place_order(order)
                self._settle_executed(result)
                return result

            account = self.broker.get_account()
            positions = self.broker.get_positions()
            position = next((p for p in positions if p.symbol.upper() == symbol), None)
            if position is not None and self._reduces(position, order):
                return self._submit_reducing(order, symbol, position, account)
            return self._submit_opening(order, symbol, positions, account)

    def _submit_opening(
        self,
        order: OrderRequest,
        symbol: str,
        positions: list[Position],
        account: AccountSnapshot,
    ) -> OrderResult:
        notional = order.quantity * order.price
        position_symbol = sum(
            (
                abs(p.quantity) * p.average_price
                for p in positions
                if p.symbol.upper() == symbol
            ),
            Decimal("0"),
        )
        group = self.risk.group_for_symbol(symbol)
        position_group = Decimal("0")
        if group and self.risk.limits.correlation_groups:
            members = {m.upper() for m in self.risk.limits.correlation_groups[group]}
            position_group = sum(
                (
                    abs(p.quantity) * p.average_price
                    for p in positions
                    if p.symbol.upper() in members
                ),
                Decimal("0"),
            )

        reserved_symbol = Decimal("0")
        reserved_group = Decimal("0")
        committed_symbol = Decimal("0")
        committed_group = Decimal("0")
        if self.reservations is not None:
            reserved_symbol = self.reservations.reserved_for_symbol(symbol)
            committed_symbol = self.reservations.committed_for_symbol(symbol)
            if group:
                reserved_group = self.reservations.reserved_for_group(group)
                committed_group = self.reservations.committed_for_group(group)

        # Broker positions and committed rows describe the SAME filled exposure, so the
        # two views are reconciled with max(), never summed. (Summing double-counted every
        # fill and roughly halved usable capacity.) max() stays conservative when either
        # view lags the other.
        symbol_exposure = max(position_symbol, committed_symbol)
        group_exposure = max(position_group, committed_group)

        decision = self.risk.evaluate(
            order,
            open_positions=account.open_positions,
            symbol_exposure=symbol_exposure,
            reserved_symbol_notional=reserved_symbol,
            correlated_exposure=group_exposure,
            reserved_group_notional=reserved_group,
            **self._pnl_inputs(account),
        )
        if not decision.allowed:
            raise PermissionError(f"order rejected by risk engine: {decision.reason}")

        reservation_id: str | None = None
        if self.reservations is not None:
            reservation_id = f"exec-{uuid4()}"
            try:
                self.reservations.reserve(
                    reservation_id,
                    symbol,
                    notional,
                    corr_group=group,
                    ttl_seconds=None,
                    max_symbol_notional=self.risk.limits.max_symbol_exposure,
                    max_group_notional=self.risk.limits.max_correlated_exposure,
                    # Only the part of the broker's view not already committed; the store
                    # adds committed + reserved itself inside its own transaction.
                    existing_symbol_exposure=max(Decimal("0"), position_symbol - committed_symbol),
                    existing_group_exposure=max(Decimal("0"), position_group - committed_group),
                    client_order_id=order.client_order_id,
                    # Atomic cross-service cap; evaluate() above is only a fast pre-check.
                    max_open_symbols=self.risk.limits.max_open_positions,
                    existing_open_symbols={p.symbol.upper() for p in positions},
                )
            except ReservationError as exc:
                raise PermissionError(f"order rejected by risk engine: {exc}") from exc

        try:
            result = self.broker.place_order(order)
        except Exception:
            if reservation_id is not None and self.reservations is not None:
                try:
                    self.reservations.release(reservation_id)
                except Exception as exc:
                    self._record_failure(
                        reservation_id=reservation_id, symbol=symbol, error=str(exc),
                        phase="rollback",
                    )
                    logger.warning(
                        "reservation release failed id=%s symbol=%s error=%s",
                        reservation_id, symbol, exc,
                    )
            raise

        if self.reservations is not None and reservation_id is not None:
            # 1) Persist the fill->commit transfer BEFORE converting, so a crash
            #    mid-conversion is recoverable. (A crash before this point is covered by
            #    the 'open' intent written inside reserve().)
            try:
                self.reservations.record_pending_transfer(
                    reservation_id=reservation_id,
                    order_id=result.order_id,
                    client_order_id=result.client_order_id,
                    symbol=symbol,
                    notional=notional,
                    corr_group=group,
                    error="pending conversion",
                )
            except Exception as record_exc:
                self._record_failure(
                    reservation_id=reservation_id, order_id=result.order_id, symbol=symbol,
                    error=str(record_exc), phase="record_pending_failed",
                )
                logger.error(
                    "failed to persist pending transfer id=%s error=%s",
                    reservation_id, record_exc,
                )
                raise ReconciliationRequiredError(
                    "paper fill succeeded but pending transfer could not be recorded; "
                    "reservation and intent retained — run reconcile_exposure()",
                    order_result=result,
                    reservation_id=reservation_id,
                    symbol=symbol,
                    notional=notional,
                    corr_group=group,
                ) from record_exc

            # 2) Convert reservation -> committed; clears pending and the intent in the
            #    same transaction. The commit is tagged with its position so the close
            #    path can release exactly this position's exposure.
            try:
                self.reservations.commit_exposure(
                    commit_id=result.order_id,
                    symbol=symbol,
                    notional=notional,
                    corr_group=group,
                    reservation_id=reservation_id,
                    position_id=symbol,
                )
            except Exception as exc:
                self._record_failure(
                    reservation_id=reservation_id, order_id=result.order_id, symbol=symbol,
                    error=str(exc), phase="commit_exposure_kept_reservation",
                )
                logger.error(
                    "commit_exposure failed; pending transfer retained for reconciliation "
                    "id=%s order_id=%s symbol=%s error=%s",
                    reservation_id, result.order_id, symbol, exc,
                )
                raise ReconciliationRequiredError(
                    "paper fill succeeded but durable exposure commit failed; "
                    "pending transfer retained — run reconcile_exposure()",
                    order_result=result,
                    reservation_id=reservation_id,
                    symbol=symbol,
                    notional=notional,
                    corr_group=group,
                ) from exc
        return result

    def _submit_reducing(
        self,
        order: OrderRequest,
        symbol: str,
        position: Position,
        account: AccountSnapshot,
    ) -> OrderResult:
        """A risk-reducing order never opens exposure, so it is never reserved."""
        held = abs(position.quantity)
        if order.quantity > held:
            # One order that both closes and reopens has ambiguous exposure accounting.
            # Fail closed: the caller closes first, then opens, as two explicit steps.
            raise PermissionError(
                "order rejected by risk engine: order would reverse the open position; "
                "close it first"
            )
        # Kill switch, staleness, daily-loss and drawdown still apply. Exposure and
        # open-position caps do not: this order can only lower them.
        decision = self.risk.evaluate(order, open_positions=0, **self._pnl_inputs(account))
        if not decision.allowed:
            raise PermissionError(f"order rejected by risk engine: {decision.reason}")

        store = self.reservations
        bound: Decimal | None = None
        intent_recorded = False
        if store is not None:
            if order.quantity < held:
                committed = store.committed_for_position(symbol, symbol)
                if committed > 0:
                    bound = committed * order.quantity / held
            intent_recorded = self._record_safety_intent(
                order.client_order_id, "reduce", symbol, bound
            )

        try:
            result = self.broker.place_order(order)
        except Exception:
            if intent_recorded:
                self._discard_intent(order.client_order_id)
            raise

        if store is not None:
            self._release_after_reduction(
                result, symbol, position, bound=bound,
                intent_id=order.client_order_id if intent_recorded else None,
                what="reduction",
            )
        return result

    def _release_after_reduction(
        self,
        result: OrderResult,
        symbol: str,
        position: Position,
        *,
        bound: Decimal | None,
        intent_id: str | None,
        what: str,
    ) -> None:
        """Release committed exposure after the broker reduced or closed a position.

        Raises ``PositionClosedReleaseFailedError`` when the broker action succeeded but
        the durable release did not: *the position moved, accounting is pending*.
        """
        assert self.reservations is not None
        store = self.reservations
        try:
            # The committed notional is authoritative: recomputing it from quantity x
            # average_price drifts under slippage and can over- or under-release.
            store.reduce_committed_for_position(
                release_id=result.order_id,
                symbol=symbol,
                position_id=symbol,
                notional=bound,
                clear_intent=intent_id,
            )
        except Exception as exc:
            if bound is not None:
                pending_notional = bound
            else:
                try:
                    outstanding = store.committed_for_symbol(symbol)
                except Exception:
                    outstanding = Decimal("0")
                pending_notional = (
                    outstanding
                    if outstanding > 0
                    else abs(position.quantity) * position.average_price
                )
            try:
                # Hands the intent's responsibility to the pending-release row atomically.
                store.record_pending_release(
                    result.order_id,
                    symbol,
                    pending_notional,
                    str(exc),
                    position_id=symbol,
                    clear_intent=intent_id,
                )
            except Exception as record_exc:
                self._record_failure(
                    release_id=result.order_id, symbol=symbol, error=str(record_exc),
                    phase="close_release_record_failed",
                )
            raise PositionClosedReleaseFailedError(
                f"position {what} succeeded but committed exposure release "
                "needs reconciliation",
                order_result=result,
                symbol=symbol,
                position_id=symbol,
            ) from exc

    # ------------------------------------------------------------------ settle / recover
    def _settle_executed(self, result: OrderResult) -> None:
        """Finish accounting for an order the broker already executed (idempotent retry)."""
        store = self.reservations
        if store is None or result.status != OrderStatus.FILLED.value:
            return
        try:
            if store.has_order_accounting(result.order_id):
                return
            intent = store.get_intent(result.client_order_id)
            if intent is not None:
                self._apply_intent_fill(intent, result)
        except Exception as exc:  # reconcile_exposure() will retry; never lose the fill
            self._record_failure(
                order_id=result.order_id, error=str(exc), phase="settle_executed_failed"
            )
            logger.warning("could not settle executed order %s: %s", result.order_id, exc)

    def _apply_intent_fill(self, intent: dict, fill: OrderResult) -> None:
        """Complete the accounting for an intent whose order is known to have filled."""
        assert self.reservations is not None
        store = self.reservations
        if intent["kind"] == "open":
            store.commit_exposure(
                commit_id=fill.order_id,
                symbol=intent["symbol"],
                notional=Decimal(intent["notional"]),
                corr_group=intent["corr_group"],
                reservation_id=intent["reservation_id"],
                position_id=intent["position_id"] or intent["symbol"],
            )
        elif intent["kind"] in {"reduce", "close"}:
            store.reduce_committed_for_position(
                release_id=fill.order_id,
                symbol=intent["symbol"],
                position_id=intent["position_id"],
                notional=Decimal(intent["notional"]) if intent["notional"] else None,
                clear_intent=intent["client_order_id"],
            )

    def _recover_intents(self, stale_after: float, reconciled: list[dict]) -> None:
        store = self.reservations
        assert store is not None
        pending_reservations = {p["reservation_id"] for p in store.list_pending_transfers()}
        now = time.time()
        for intent in store.list_intents():
            cid = intent["client_order_id"]
            kind = intent["kind"]
            stale = (now - intent["created_at"]) >= stale_after
            try:
                if not self._can_lookup:
                    continue  # cannot tell whether it executed; never guess
                if kind == "open" and intent["reservation_id"] in pending_reservations:
                    continue  # the pending-transfer path already owns this one
                fill = self._lookup_order(cid)
                if fill is not None and fill.status == OrderStatus.FILLED.value:
                    self._apply_intent_fill(intent, fill)
                    reconciled.append({**intent, "action": "settled_fill"})
                elif fill is None and stale:
                    if kind == "open":
                        store.release(intent["reservation_id"])
                    else:
                        store.discard_intent(cid)
                    reconciled.append({**intent, "action": "released_unexecuted"})
            except Exception as exc:
                logger.warning(
                    "reconcile_exposure could not resolve intent id=%s kind=%s error=%s",
                    cid, kind, exc,
                )

    def reconcile_exposure(self, *, stale_after_seconds: float | None = None) -> list[dict]:
        """Resolve everything a crash or failure left behind, including after restart.

        ``stale_after_seconds`` is the age before an intent whose order never reached the
        broker is released; it protects a submission that is genuinely still in flight.
        Defaults to the service's ``stale_intent_seconds``.
        """
        if self.reservations is None:
            return []
        stale_after = (
            self.stale_intent_seconds if stale_after_seconds is None else float(stale_after_seconds)
        )
        reconciled: list[dict] = []
        with self._submission_lock:
            for item in self.reservations.list_pending_transfers():
                try:
                    self.reservations.commit_exposure(
                        commit_id=item["order_id"],
                        symbol=item["symbol"],
                        notional=Decimal(item["notional"]),
                        corr_group=item.get("corr_group"),
                        reservation_id=item["reservation_id"],
                        # Keep the position link submit() uses for its commits.
                        # Omitting it writes a legacy symbol-wide row that can
                        # never be released by position, so a crash-recovered
                        # entry would permanently consume capacity.
                        position_id=item.get("position_id") or item["symbol"],
                    )
                    reconciled.append(dict(item))
                    logger.info(
                        "reconciled exposure order_id=%s reservation_id=%s",
                        item["order_id"], item["reservation_id"],
                    )
                except Exception as exc:
                    logger.warning(
                        "reconcile_exposure still failing order_id=%s error=%s",
                        item["order_id"], exc,
                    )
            for item in self.reservations.list_pending_releases():
                try:
                    # Retry with the notional that was recorded. Passing none means
                    # "release every commit for this position", which would
                    # over-release a queued partial close.
                    self.reservations.reduce_committed_for_position(
                        release_id=item["release_id"],
                        symbol=item["symbol"],
                        position_id=item.get("position_id"),
                        notional=Decimal(item["notional"]),
                    )
                    reconciled.append(dict(item))
                except Exception as exc:
                    logger.warning(
                        "reconcile_exposure still failing release_id=%s error=%s",
                        item["release_id"], exc,
                    )
            self._recover_intents(stale_after, reconciled)
        return reconciled

    # ------------------------------------------------------------------ close
    def close_position(self, symbol: str, price: Decimal) -> OrderResult:
        """Close a paper position and release the exposure it committed.

        A 'close' intent is written first, so a crash between the broker close and the
        release is recoverable: after a restart ``reconcile_exposure()`` looks the closing
        order up by its client ID and applies the release only if it really executed.

        Raises ``PositionClosedReleaseFailedError`` when the broker close
        succeeded but the durable release did not. That is deliberately a
        distinct type from a failed close: the position *is* flat, and the
        release is queued for ``reconcile_exposure()``.
        """
        with self._submission_lock:
            if not price.is_finite() or price <= 0:
                raise ValueError("close price must be a finite positive value")
            normalized = symbol.strip().upper()
            positions = {
                position.symbol.upper(): position for position in self.broker.get_positions()
            }
            position = positions.get(normalized)
            if position is None:
                raise ValueError(f"no open position for {normalized}")

            # The closing order's client ID is chosen BEFORE the broker call and doubles as the
            # intent key, so recovery can look the exact order up at the broker instead of
            # inferring the outcome from whether the position happens to be flat.
            close_id = f"close-{uuid4()}"
            intent_id: str | None = None
            if self.reservations is not None and self._record_safety_intent(
                close_id, "close", normalized, None
            ):
                intent_id = close_id

            try:
                result = self.broker.close_position(normalized, price, client_order_id=close_id)
            except Exception:
                if intent_id is not None:
                    self._discard_intent(intent_id)
                raise

            if self.reservations is not None:
                self._release_after_reduction(
                    result, normalized, position, bound=None, intent_id=intent_id, what="close"
                )
            return result
