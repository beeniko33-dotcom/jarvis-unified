"""Jarvis Unified entrypoint. Paper mode only at this maturity level."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from decimal import Decimal
from core.config import Settings
from core.risk import RiskEngine, RiskLimits
from brokers.paper import PaperBroker

def build_runtime(settings: Settings):
    broker = PaperBroker(settings.starting_balance)
    risk = RiskEngine(RiskLimits(settings.max_stake_per_trade, settings.max_daily_loss, settings.max_open_positions, settings.kill_switch))
    return broker, risk

def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis Unified — paper-first trading infrastructure")
    parser.add_argument("--check", action="store_true", help="validate configuration and initialize paper runtime")
    parser.add_argument("--serve", action="store_true", help="start localhost read-only status API")
    args = parser.parse_args()
    settings = Settings.from_env()
    broker, risk = build_runtime(settings)
    if args.check:
        print("Configuration valid; paper broker initialized; kill_switch=" + str(risk.halted))
        return
    if args.serve:
        from apps.api.status import serve
        def status():
            account = broker.get_account()
            return {"mode": settings.mode, "broker": "paper", "kill_switch": risk.halted, "account": asdict(account), "positions": [asdict(p) for p in broker.get_positions()]}
        serve(settings.status_host, settings.status_port, status)
        return
    parser.print_help()

if __name__ == "__main__": main()
