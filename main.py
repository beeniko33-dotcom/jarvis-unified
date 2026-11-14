"""Jarvis Unified entrypoint. Paper mode only at this maturity level."""
from __future__ import annotations
import argparse
import dataclasses
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
    from core.feature_registry import feature_state_inventory

    account = broker.get_account()
    return {
        "mode": settings.mode,
        "broker": "paper",
        "feature_inventory": feature_state_inventory(),
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


def print_banner(*, container_bind: bool = False) -> None:
    print("Jarvis Unified")
    print("Paper-first broker-agnostic trading runtime")
    if container_bind:
        print("Status: safe / read-only / bind-all; publish the container port to localhost only")
    else:
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
    parser.add_argument("--serve", action="store_true", help="start read-only status API")
    parser.add_argument(
        "--container-bind",
        action="store_true",
        help="allow a container-interface bind; publish the port to localhost only",
    )
    parser.add_argument("--host", help="bind address for status API; must remain localhost-only")
    parser.add_argument("--port", type=int, help="port for status API")

    parser.add_argument("--memory-db", default="var/learning/memory.sqlite3",
                        help="SQLite path for personal learning memories")
    parser.add_argument("--memory-list", action="store_true",
                        help="list saved personal preferences as JSON")
    parser.add_argument("--remember", nargs=3, metavar=("CATEGORY", "KEY", "CONTENT"),
                        help="explicitly save a personal preference")
    parser.add_argument("--forget", nargs=2, metavar=("CATEGORY", "KEY"),
                        help="delete a saved personal preference")
    parser.add_argument("--personality-context", action="store_true",
                        help="print Jarvis core personality plus saved preference context")
    parser.add_argument("--learning-db", default="var/learning/observations.sqlite3",
                        help="SQLite path for the tamper-evident paper learning journal")
    parser.add_argument("--paper-ledger-db",
                        help="path to an existing persistent paper broker ledger")
    learning_actions = parser.add_mutually_exclusive_group()
    learning_actions.add_argument("--import-paper-ledger", action="store_true",
                                  help="verify and import a paper ledger into the learning journal")
    learning_actions.add_argument("--paper-outcomes", action="store_true",
                                  help="print loss-inclusive paper outcome analytics")
    learning_actions.add_argument("--paper-reflections", action="store_true",
                                  help="build factual reflections from verified learning-journal events")
    learning_actions.add_argument("--shadow-review", action="store_true",
                                  help="generate evidence-linked, advisory-only learning candidates")
    learning_actions.add_argument("--shadow-history", action="store_true",
                                  help="list persistent shadow candidates and owner review history")
    learning_actions.add_argument("--shadow-decision", nargs=2, metavar=("CANDIDATE_ID", "DECISION"),
                                  help="append an owner review decision; never deploys a strategy")
    learning_actions.add_argument("--experiment-list", action="store_true",
                                  help="list immutable experiment metadata")
    learning_actions.add_argument("--experiment-verify", metavar="EXPERIMENT_ID",
                                  help="verify stored config and metrics hashes")
    learning_actions.add_argument("--experiment-verify-sources", nargs=3,
                                  metavar=("EXPERIMENT_ID", "LEDGER_FILE", "JOURNAL_FILE"),
                                  help="hash local source artifacts and append a verification result")
    learning_actions.add_argument("--experiment-compare", nargs=2,
                                  metavar=("LEFT_EXPERIMENT_ID", "RIGHT_EXPERIMENT_ID"),
                                  help="compare experiments only when evidence is strictly comparable")
    parser.add_argument("--experience-db", default="var/learning/experience.sqlite3",
                        help="SQLite path for the immutable experiment registry")
    parser.add_argument("--shadow-notes", default="", help="optional note for an owner review decision")
    parser.add_argument("--shadow-db", default="var/learning/shadow_candidates.sqlite3",
                        help="SQLite path for persistent shadow recommendation history")
    parser.add_argument("--reflection-db", default="var/learning/reflections.sqlite3",
                        help="SQLite path for factual session reflection history")
    args = parser.parse_args(argv)
    if args.container_bind:
        other_actions = (
            args.check,
            args.health,
            args.summary,
            args.status,
            args.version,
            args.report,
            args.demo,
            args.memory_list,
            args.remember,
            args.forget,
            args.personality_context,
            args.import_paper_ledger,
            args.paper_outcomes,
            args.paper_reflections,
            args.shadow_review,
            args.shadow_history,
            args.shadow_decision,
            args.experiment_list,
            args.experiment_verify,
            args.experiment_verify_sources,
            args.experiment_compare,
        )
        if (
            not args.serve
            or args.host is not None
            or args.port is not None
            or any(other_actions)
        ):
            raise ValueError("--container-bind requires --serve as the only action")

    if args.memory_list or args.remember or args.forget or args.personality_context:
        from dataclasses import asdict
        from core.learning.memory_store import MemoryStore
        from core.learning.personality import build_personality_context

        memory = MemoryStore(args.memory_db)
        if args.remember:
            item = memory.put(*args.remember, source="explicit_user_feedback", confidence=1.0)
            print(json.dumps(asdict(item), indent=2))
            return
        if args.forget:
            print(json.dumps({"deleted": memory.delete(*args.forget)}))
            return
        if args.memory_list:
            print(memory.export_json())
            return
        if args.personality_context:
            print(build_personality_context(memory))
            return

    if (args.experiment_list or args.experiment_verify
            or args.experiment_verify_sources or args.experiment_compare):
        from research.experience_store import ExperienceStore
        store = ExperienceStore(args.experience_db)
        if args.experiment_list:
            print(json.dumps({
                "experiments": [dataclasses.asdict(item) for item in store.list()],
            }, indent=2, default=str))
            return
        if args.experiment_verify:
            print(json.dumps({
                "experiment_id": args.experiment_verify,
                "integrity_verified": store.verify(args.experiment_verify),
            }, indent=2))
            return
        if args.experiment_verify_sources:
            experiment_id, ledger_path, journal_path = args.experiment_verify_sources
            print(json.dumps(store.verify_source_artifacts(
                experiment_id, ledger_path=ledger_path, journal_path=journal_path,
            ), indent=2))
            return
        if args.experiment_compare:
            from research.experiment_comparison import compare_experiments
            report = compare_experiments(store, *args.experiment_compare)
            print(json.dumps(report.to_dict(), indent=2, default=str))
            return

    if (args.import_paper_ledger or args.paper_outcomes or args.paper_reflections
            or args.shadow_review or args.shadow_history or args.shadow_decision):
        from pathlib import Path
        from research.execution_observations import ExecutionObservationJournal
        from research.shadow_advisor import ShadowCandidateStore

        shadow_store = None
        if args.shadow_history or args.shadow_decision or args.shadow_review:
            shadow_store = ShadowCandidateStore(args.shadow_db)
        if args.shadow_history:
            print(json.dumps({"candidate_history": shadow_store.list_candidates(
                include_expired=True
            )}, indent=2, default=str))
            return
        if args.shadow_decision:
            candidate_id, decision = args.shadow_decision
            shadow_store.record_owner_decision(
                candidate_id, decision, notes=args.shadow_notes
            )
            print(json.dumps({"recorded": True, "candidate_id": candidate_id,
                              "decision": decision}, indent=2))
            return
        if args.import_paper_ledger and not args.paper_ledger_db:
            parser.error("--import-paper-ledger requires --paper-ledger-db")
        if (args.paper_outcomes or args.paper_reflections or args.shadow_review) and not Path(args.learning_db).is_file():
            parser.error("paper learning reports require an existing --learning-db")
        journal = ExecutionObservationJournal(args.learning_db)
        if args.import_paper_ledger:
            from dataclasses import asdict
            from research.paper_ledger_importer import import_paper_ledger

            result = import_paper_ledger(args.paper_ledger_db, journal)
            print(json.dumps(asdict(result), indent=2, default=str))
            return
        from research.paper_outcomes import build_paper_outcome_report

        if args.paper_reflections:
            from dataclasses import asdict
            from research.paper_reflection_bridge import build_paper_reflections
            from research.reflection import ReflectionStore

            reflections = build_paper_reflections(
                journal, ReflectionStore(args.reflection_db)
            )
            print(json.dumps({
                "reflection_count": len(reflections),
                "reflections": [asdict(item) for item in reflections],
            }, indent=2, default=str))
            return
        report = build_paper_outcome_report(journal)
        if args.shadow_review:
            from research.shadow_advisor import generate_shadow_candidates

            candidates = generate_shadow_candidates(report, shadow_store)
            print(json.dumps({
                "report": report.to_dict(),
                "candidates": [item.to_dict() for item in candidates],
                "candidate_history": shadow_store.list_candidates(),
            }, indent=2, default=str))
            return
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return

    settings = Settings.from_env()
    broker, risk = build_runtime(settings)

    host = "0.0.0.0" if args.container_bind else args.host or settings.status_host
    port = args.port if args.port is not None else settings.status_port
    if not args.container_bind and host not in {"127.0.0.1", "localhost"}:
        raise ValueError(
            "Status API may only bind to localhost until authentication and TLS are configured"
        )

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
        print_banner(container_bind=args.container_bind)
        from apps.api.status import serve

        def status():
            return build_status_payload(broker, settings, risk)

        try:
            serve(host, port, status, allow_container_bind=args.container_bind)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        return
    parser.print_help()


if __name__ == "__main__":
    main()
