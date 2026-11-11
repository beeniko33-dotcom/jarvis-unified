"""Jarvis Unified entrypoint. Paper mode only at this maturity level."""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from typing import Sequence

from core.config import Settings
from core.risk import RiskEngine, RiskLimits
from brokers.paper import PaperBroker


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
    if args.health:
        print(json.dumps({"ok": True}))
        return
    if args.summary:
        print(json.dumps(build_summary_payload(broker, settings, risk), default=str))
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
