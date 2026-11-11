"""Jarvis Unified entrypoint. Paper mode only at this maturity level."""
from __future__ import annotations
import argparse
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Jarvis Unified — paper-first trading infrastructure")
    parser.add_argument("--check", action="store_true", help="validate configuration and initialize paper runtime")
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
        print("Configuration valid; paper broker initialized; kill_switch=" + str(risk.halted))
        return
    if args.serve:
        from apps.api.status import serve

        def status():
            account = broker.get_account()
            return {
                "mode": settings.mode,
                "broker": "paper",
                "kill_switch": risk.halted,
                "account": asdict(account),
                "positions": [asdict(p) for p in broker.get_positions()],
            }

        serve(host, port, status)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
