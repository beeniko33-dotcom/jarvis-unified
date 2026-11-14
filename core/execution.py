"""The only supported path from strategy orders to a broker adapter."""
from __future__ import annotations

import logging
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from brokers.base import Broker
from core.models import OrderRequest, OrderResult
from core.risk import ExposureReservationStore, ReservationError, RiskEngine
from research.execution_observations import ExecutionObservationJournal

logger = logging.getLogger(__name__)


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


class ExecutionObservationPersistenceError(RuntimeError):
    """The paper broker action completed but its learning observation did not persist."""

    def __init__(self, message: str, *, order_result: OrderResult) -> None:
        super().__init__(message)
        self.order_result = order_result


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
        observation_journal: ExecutionObservationJournal | None = None,
    ) -> None:
        self.broker = broker
        self.risk = risk
        self.reservations = reservations
        self.observation_journal = observation_journal
        self._submission_lock = RLock()
        self._release_failures: list[dict] = []

    @property
    def release_failures(self) -> list[dict]:
        with self._submission_lock:
            return list(self._release_failures)

    @property
    def pending_reconciliation(self) -> list[dict]:
        if self.reservations is None:
            return []
        return self.reservations.list_pending_transfers()

    def _record_observation(self, event_id: str, event_type: str, data: dict) -> None:
        if self.observation_journal is None:
            return
        # JSON round-trip with string fallback preserves Decimal/datetime metadata
        # without silently dropping values or making assumptions about their schema.
        import json
        safe_data = json.loads(json.dumps(data, default=str, sort_keys=True))
        self.observation_journal.append(
            event_id=event_id, event_type=event_type, data=safe_data
        )

    def submit(self, order: OrderRequest) -> OrderResult:
        reservation_id: str | None = None
        with self._submission_lock:
            if (
                self.observation_journal is not None
                and self.observation_journal.has_event(f"decision:{order.client_order_id}")
            ):
                raise PermissionError(
                    "client_order_id already has an execution observation; "
                    "reconcile the prior attempt and use a new ID for a new order"
                )
            account = self.broker.get_account()
            unrealized_pnl = account.equity - account.balance
            positions = self.broker.get_positions()
            symbol = order.symbol.strip().upper()
            notional = order.quantity * order.price
            symbol_exposure = sum(
                (
                    abs(position.quantity) * position.average_price
                    for position in positions
                    if position.symbol.upper() == symbol
                ),
                Decimal("0"),
            )
            group = self.risk.group_for_symbol(symbol)
            correlated_exposure = Decimal("0")
            if group and self.risk.limits.correlation_groups:
                members = {m.upper() for m in self.risk.limits.correlation_groups[group]}
                correlated_exposure = sum(
                    (
                        abs(position.quantity) * position.average_price
                        for position in positions
                        if position.symbol.upper() in members
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

            decision = self.risk.evaluate(
                order,
                daily_realized_pnl=(
                    account.daily_realized_pnl if account.daily_accounting_available
                    else account.realized_pnl
                ),
                unrealized_pnl=unrealized_pnl,
                commission_paid=(
                    account.daily_commission_paid if account.daily_accounting_available
                    else account.commission_paid
                ),
                open_positions=account.open_positions,
                # The committed ledger is a durable *mirror* of filled exposure,
                # not additional exposure on top of it. While the broker is
                # alive both describe the same fills, so summing them doubles
                # the real exposure and trips the cap at half its value. After
                # a restart of an in-memory broker the live positions are gone
                # and the committed rows are the only surviving record, so the
                # larger of the two is the correct figure in both cases.
                symbol_exposure=max(symbol_exposure, committed_symbol),
                reserved_symbol_notional=reserved_symbol,
                correlated_exposure=max(correlated_exposure, committed_group),
                reserved_group_notional=reserved_group,
                current_equity=account.equity,
                peak_equity=account.peak_equity,
            )
            observation = {
                "client_order_id": order.client_order_id,
                "symbol": symbol,
                "side": order.side.value if hasattr(order.side, "value") else str(order.side),
                "quantity": str(order.quantity),
                "requested_price": str(order.price),
                "notional": str(notional),
                "strategy_id": order.metadata.get("strategy_id"),
                "strategy_version": order.metadata.get("strategy_version"),
                "strategy_config_hash": order.metadata.get("strategy_config_hash"),
                "experiment_id": order.metadata.get("experiment_id"),
                "quote_source": order.metadata.get("quote_source"),
                "quote_timestamp": order.metadata.get("quote_timestamp"),
                "metadata": dict(order.metadata),
                "risk_reason": decision.reason,
            }
            self._record_observation(
                f"decision:{order.client_order_id}",
                "risk_approved" if decision.allowed else "risk_rejected",
                observation,
            )
            if not decision.allowed:
                raise PermissionError(f"order rejected by risk engine: {decision.reason}")

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
                        existing_symbol_exposure=symbol_exposure,
                        existing_group_exposure=correlated_exposure,
                    )
                except ReservationError as exc:
                    rejected = dict(observation)
                    rejected["risk_reason"] = str(exc)
                    self._record_observation(
                        f"reservation-rejected:{order.client_order_id}",
                        "reservation_rejected",
                        rejected,
                    )
                    raise PermissionError(f"order rejected by risk engine: {exc}") from exc

            try:
                result = self.broker.place_order(order)
            except Exception as broker_exc:
                failed = dict(observation)
                failed["error_type"] = type(broker_exc).__name__
                failed["error"] = str(broker_exc)
                self._record_observation(
                    f"broker-error:{order.client_order_id}", "broker_submission_error", failed
                )
                if reservation_id is not None and self.reservations is not None:
                    try:
                        self.reservations.release(reservation_id)
                    except Exception as exc:
                        self._release_failures.append(
                            {
                                "reservation_id": reservation_id,
                                "symbol": symbol,
                                "error": str(exc),
                                "phase": "rollback",
                            }
                        )
                        logger.warning(
                            "reservation release failed id=%s symbol=%s error=%s",
                            reservation_id,
                            symbol,
                            exc,
                        )
                raise

            try:
                filled = dict(observation)
                filled.update({
                    "order_id": result.order_id,
                    "result_status": result.status,
                    "fill_price": str(result.fill_price),
                    "filled_quantity": str(result.filled_quantity),
                    "remaining_quantity": str(result.remaining_quantity),
                    "created_at": result.created_at.isoformat(),
                })
                self._record_observation(
                    f"broker-result:{result.client_order_id}", "broker_order_result", filled
                )
            except Exception as exc:
                raise ExecutionObservationPersistenceError(
                    "paper broker action completed but its observation was not persisted; "
                    "reconcile against the broker ledger before retrying",
                    order_result=result,
                ) from exc

            if self.reservations is not None and reservation_id is not None:
                # 1) Persist intent BEFORE conversion so a crash mid-commit is recoverable.
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
                    self._release_failures.append(
                        {
                            "reservation_id": reservation_id,
                            "order_id": result.order_id,
                            "symbol": symbol,
                            "error": str(record_exc),
                            "phase": "record_pending_failed",
                        }
                    )
                    logger.error(
                        "failed to persist pending transfer id=%s error=%s",
                        reservation_id,
                        record_exc,
                    )
                    raise ReconciliationRequiredError(
                        "paper fill succeeded but pending transfer could not be recorded; "
                        "reservation retained — manual reconcile may be required",
                        order_result=result,
                        reservation_id=reservation_id,
                        symbol=symbol,
                        notional=notional,
                        corr_group=group,
                    ) from record_exc

                # 2) Convert reservation → committed; clears pending in the same txn.
                #    The commit is tagged with the position it belongs to so the
                #    close path can release exactly this position's exposure.
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
                    self._release_failures.append(
                        {
                            "reservation_id": reservation_id,
                            "order_id": result.order_id,
                            "symbol": symbol,
                            "error": str(exc),
                            "phase": "commit_exposure_kept_reservation",
                        }
                    )
                    logger.error(
                        "commit_exposure failed; pending transfer retained for reconciliation "
                        "id=%s order_id=%s symbol=%s error=%s",
                        reservation_id,
                        result.order_id,
                        symbol,
                        exc,
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

    def reconcile_exposure(self) -> list[dict]:
        """Complete pending reservation→committed transfers, including after restart."""
        if self.reservations is None:
            return []
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
                        item["order_id"],
                        item["reservation_id"],
                    )
                except Exception as exc:
                    logger.warning(
                        "reconcile_exposure still failing order_id=%s error=%s",
                        item["order_id"],
                        exc,
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
        return reconciled

    def close_position(self, symbol: str, price: Decimal) -> OrderResult:
        """Close a paper position and release the exposure it committed.

        Raises ``PositionClosedReleaseFailedError`` when the broker close
        succeeded but the durable release did not. That is deliberately a
        distinct type from a failed close: the position *is* flat, and the
        release is queued for ``reconcile_exposure()``.
        """
        with self._submission_lock:
            if not price.is_finite() or price <= 0:
                raise ValueError("close price must be a finite positive value")
            normalized = symbol.strip().upper()
            positions = {position.symbol.upper(): position for position in self.broker.get_positions()}
            position = positions.get(normalized)
            if position is None:
                raise ValueError(f"no open position for {normalized}")
            result = self.broker.close_position(normalized, price)
            try:
                self._record_observation(
                    f"position-close:{result.order_id}",
                    "position_close_result",
                    {
                        "order_id": result.order_id,
                        "client_order_id": result.client_order_id,
                        "symbol": normalized,
                        "requested_price": str(price),
                        "fill_price": str(result.fill_price),
                        "quantity": str(result.quantity),
                        "filled_quantity": str(result.filled_quantity),
                        "status": result.status,
                        "created_at": result.created_at.isoformat(),
                    },
                )
            except Exception as exc:
                raise ExecutionObservationPersistenceError(
                    "paper position close completed but its observation was not persisted; "
                    "reconcile against the broker ledger before retrying",
                    order_result=result,
                ) from exc
            if self.reservations is not None:
                # Release what was actually committed for this position. The
                # committed notional is authoritative: recomputing it from
                # quantity x average_price drifts under slippage and can
                # over- or under-release.
                try:
                    self.reservations.reduce_committed_for_position(
                        release_id=result.order_id,
                        symbol=normalized,
                        position_id=normalized,
                    )
                except Exception as exc:
                    # Record what is actually committed for this position, not a
                    # recomputed quantity x average_price. A slippage-adjusted
                    # average can sit either side of the committed notional, so a
                    # recomputed bound would under- or over-release on retry.
                    try:
                        outstanding = self.reservations.committed_for_symbol(normalized)
                    except Exception:
                        outstanding = Decimal("0")
                    try:
                        self.reservations.record_pending_release(
                            result.order_id,
                            normalized,
                            outstanding
                            if outstanding > 0
                            else abs(position.quantity) * position.average_price,
                            str(exc),
                            position_id=normalized,
                        )
                    except Exception as record_exc:
                        self._release_failures.append({
                            "release_id": result.order_id,
                            "symbol": normalized,
                            "error": str(record_exc),
                            "phase": "close_release_record_failed",
                        })
                    raise PositionClosedReleaseFailedError(
                        "position close succeeded but committed exposure release "
                        "needs reconciliation",
                        order_result=result,
                        symbol=normalized,
                        position_id=normalized,
                    ) from exc
            return result
