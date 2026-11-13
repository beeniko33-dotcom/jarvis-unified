"""Jarvis Unified entrypoint. Paper mode only at this maturity level."""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from typing import Sequence

from brokers.paper import PaperBroker
from core.config import Settings
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.risk import RiskEngine, RiskLimits

APP_VERSION = "0.2.0"


def build_runtime(settings: Settings):
    broker = PaperBroker(settings.starting_balance)
    risk = RiskEngine(
        RiskLimits(
            settings.max_stake_per_trade,
            settings.max_daily_loss,
            settings.max_open_positions,
            settings.kill_switch,
        )
    )
    return broker, risk


def build_status_payload(broker, settings, risk) -> dict:
    account = broker.get_account()
    return {
        "mode": settings.mode,
        "broker": "paper",
        "kill_switch": risk.halted,
        "account": asdict(account),
        "positions": [asdict(p) for p in broker.get_positions()],
    }


def build_summary_payload(broker, settings, risk) -> dict:
    status = build_status_payload(broker, settings, risk)
    return {
        "ok": True,
        "mode": status["mode"],
        "broker": status["broker"],
        "kill_switch": status["kill_switch"],
        "open_positions": len(status["positions"]),
        "balance": status["account"]["balance"],
        "equity": status["account"]["equity"],
        "version": APP_VERSION,
    }


def build_demo_payload(broker, settings, risk) -> dict:
    execution = ExecutionService(broker, risk)
    if risk.halted:
        risk.release_kill_switch(explicit_operator_action=True)

    approved_order = OrderRequest(
        symbol="AAPL",
        side=Side.BUY,
        quantity=Decimal("0.02"),
        price=Decimal("100.00"),
        client_order_id="demo-buy-001",
    )
    approved = execution.submit(approved_order)

    rejected_order = OrderRequest(
        symbol="MSFT",
        side=Side.BUY,
        quantity=Decimal("200"),
        price=Decimal("1000.00"),
        client_order_id="demo-reject-001",
    )
    rejected = {"allowed": False, "reason": "not attempted"}
    try:
        execution.submit(rejected_order)
    except PermissionError as exc:
        rejected = {"allowed": False, "reason": str(exc)}

    closed = execution.close_position(approved.symbol, approved.fill_price)
    risk.engage_kill_switch()
    account = broker.get_account()
    return {
        "ok": True,
        "demo": True,
        "version": APP_VERSION,
        "mode": settings.mode,
        "broker": "paper",
        "kill_switch": risk.halted,
        "approved_order": {
            "order_id": approved.order_id,
            "symbol": approved.symbol,
            "side": approved.side.value,
            "quantity": str(approved.quantity),
            "fill_price": str(approved.fill_price),
            "created_at": approved.created_at.isoformat(),
        },
        "closed_order": {
            "order_id": closed.order_id,
            "symbol": closed.symbol,
            "side": closed.side.value,
            "quantity": str(closed.quantity),
            "fill_price": str(closed.fill_price),
        },
        "rejected_order": rejected,
        "account": {
            "balance": str(account.balance),
            "equity": str(account.equity),
            "realized_pnl": str(account.realized_pnl),
            "open_positions": account.open_positions,
        },
        "summary": build_summary_payload(broker, settings, risk),
    }


def print_banner() -> None:
    print("Jarvis Unified")
    print("Paper-first broker-agnostic trading runtime")
    print("Status: safe / read-only / localhost-only")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Jarvis Unified — paper-first trading infrastructure")
    parser.add_argument("--check", action="store_true", help="validate configuration and initialize paper runtime")
    parser.add_argument("--health", action="store_true", help="print a minimal JSON health payload")
    parser.add_argument("--summary", action="store_true", help="print a concise JSON summary snapshot")
    parser.add_argument("--status", action="store_true", help="print a JSON status snapshot without starting the API")
    parser.add_argument("--version", action="store_true", help="print the application version")
    parser.add_argument("--report", action="store_true", help="print a combined version + health + summary snapshot")
    parser.add_argument("--demo", action="store_true", help="execute a paper-trading demo and print a richer snapshot")
    parser.add_argument("--serve", action="store_true", help="start localhost read-only status API")
    parser.add_argument("--host", help="bind address for status API; must remain localhost-only")
    parser.add_argument("--port", type=int, help="port for status API")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    broker, risk = build_runtime(settings)

    host = args.host or settings.status_host
    port = args.port if args.port is not None else settings.status_port
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Status API may only bind to localhost until authentication and TLS are configured")

    if args.check:
        print_banner()
        print("Configuration valid; paper broker initialized; kill_switch=" + str(risk.halted))
        return
    if args.version:
        print(f"Jarvis Unified {APP_VERSION}")
        return
    if args.health:
        print(json.dumps({"ok": True}))
        return
    if args.summary:
        print(json.dumps(build_summary_payload(broker, settings, risk), default=str))
        return
    if args.report:
        report = build_summary_payload(broker, settings, risk)
        report["version"] = APP_VERSION
        report["ok"] = True
        print(json.dumps(report, default=str))
        return
    if args.demo:
        print_banner()
        print(json.dumps(build_demo_payload(broker, settings, risk), default=str))
        return
    if args.status:
        print_banner()
        print(json.dumps(build_status_payload(broker, settings, risk), default=str))
        return
    if args.serve:
        print_banner()
        from apps.api.status import serve

        def status():
            return build_status_payload(broker, settings, risk)

        try:
            serve(host, port, status)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        return
    parser.print_help()


if __name__ == "__main__":
    main()
