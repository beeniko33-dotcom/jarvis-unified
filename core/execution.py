"""The only supported path from strategy orders to a broker adapter."""
from __future__ import annotations

import logging
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from brokers.base import Broker
from core.models import OrderRequest, OrderResult
from core.risk import ExposureReservationStore, ReservationError, RiskEngine

logger = logging.getLogger(__name__)


class ReconciliationRequiredError(RuntimeError):
    """Paper fill succeeded but durable exposure commit did not.

    The temporary reservation is intentionally retained so capacity remains
    conservative until reconcile_exposure() completes the transfer.
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


class ExecutionService:
    def __init__(
        self,
        broker: Broker,
        risk: RiskEngine,
        *,
        reservations: ExposureReservationStore | None = None,
    ) -> None:
        self.broker = broker
        self.risk = risk
        self.reservations = reservations
        # Process-local serialization. Cross-process capacity uses the reservation store.
        self._submission_lock = RLock()
        self._release_failures: list[dict] = []
        self._pending_reconciliation: list[dict] = []

    @property
    def release_failures(self) -> list[dict]:
        with self._submission_lock:
            return list(self._release_failures)

    @property
    def pending_reconciliation(self) -> list[dict]:
        with self._submission_lock:
            return list(self._pending_reconciliation)

    def submit(self, order: OrderRequest) -> OrderResult:
        """Submit after risk check and atomic capacity reservation when configured."""
        reservation_id: str | None = None
        with self._submission_lock:
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
                symbol_exposure=symbol_exposure + committed_symbol,
                reserved_symbol_notional=reserved_symbol,
                correlated_exposure=correlated_exposure + committed_group,
                reserved_group_notional=reserved_group,
                current_equity=account.equity,
                peak_equity=account.peak_equity,
            )
            if not decision.allowed:
                raise PermissionError(f"order rejected by risk engine: {decision.reason}")

            if self.reservations is not None:
                reservation_id = f"exec-{uuid4()}"
                try:
                    # No TTL until commit_exposure converts or explicit release on broker failure.
                    # Prevents exposure from disappearing during the fill->commit window.
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
                    raise PermissionError(f"order rejected by risk engine: {exc}") from exc

            try:
                result = self.broker.place_order(order)
            except Exception:
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

            if self.reservations is not None and reservation_id is not None:
                try:
                    self.reservations.commit_exposure(
                        commit_id=result.order_id,
                        symbol=symbol,
                        notional=notional,
                        corr_group=group,
                        reservation_id=reservation_id,
                    )
                except Exception as exc:
                    # Keep the reservation so capacity stays conservative.
                    # Do not release. Operator must call reconcile_exposure().
                    pending = {
                        "reservation_id": reservation_id,
                        "order_id": result.order_id,
                        "client_order_id": result.client_order_id,
                        "symbol": symbol,
                        "notional": str(notional),
                        "corr_group": group,
                        "error": str(exc),
                    }
                    self._pending_reconciliation.append(pending)
                    self._release_failures.append(
                        {
                            **pending,
                            "phase": "commit_exposure_kept_reservation",
                        }
                    )
                    logger.error(
                        "commit_exposure failed; reservation retained for reconciliation "
                        "id=%s order_id=%s symbol=%s error=%s",
                        reservation_id,
                        result.order_id,
                        symbol,
                        exc,
                    )
                    raise ReconciliationRequiredError(
                        "paper fill succeeded but durable exposure commit failed; "
                        "reservation retained — run reconcile_exposure()",
                        order_result=result,
                        reservation_id=reservation_id,
                        symbol=symbol,
                        notional=notional,
                        corr_group=group,
                    ) from exc
            return result

    def reconcile_exposure(self) -> list[dict]:
        """Complete pending reservation→committed transfers after a commit failure.

        Safe to call repeatedly. For each pending item, attempts commit_exposure
        using the retained reservation_id. Successful items are removed from the
        pending list. Returns the list of successfully reconciled records.
        """
        if self.reservations is None:
            return []
        reconciled: list[dict] = []
        with self._submission_lock:
            remaining: list[dict] = []
            for item in self._pending_reconciliation:
                try:
                    self.reservations.commit_exposure(
                        commit_id=item["order_id"],
                        symbol=item["symbol"],
                        notional=Decimal(item["notional"]),
                        corr_group=item.get("corr_group"),
                        reservation_id=item["reservation_id"],
                    )
                    reconciled.append(dict(item))
                    logger.info(
                        "reconciled exposure order_id=%s reservation_id=%s",
                        item["order_id"],
                        item["reservation_id"],
                    )
                except Exception as exc:
                    item = dict(item)
                    item["last_error"] = str(exc)
                    remaining.append(item)
                    logger.warning(
                        "reconcile_exposure still failing order_id=%s error=%s",
                        item["order_id"],
                        exc,
                    )
            self._pending_reconciliation = remaining
        return reconciled

    def close_position(self, symbol: str, price: Decimal) -> OrderResult:
        """Close an existing paper position; risk stops new entries, not risk-reducing exits."""
        with self._submission_lock:
            if not price.is_finite() or price <= 0:
                raise ValueError("close price must be a finite positive value")
            positions = {position.symbol: position for position in self.broker.get_positions()}
            if symbol not in positions:
                raise ValueError(f"no open position for {symbol}")
            return self.broker.close_position(symbol, price)
