"""Read-only inventory of shipped, experimental, and unavailable capabilities.

This registry is descriptive only. It deliberately exposes no mutation or toggle API.
"""
from __future__ import annotations

from copy import deepcopy


_FEATURES = (
    {
        "id": "paper_execution",
        "name": "Paper execution",
        "state": "enabled",
        "maturity": "operational",
        "reason": "The only supported execution mode; orders pass through ExecutionService and central risk checks.",
        "dependencies": ["central_risk_engine", "paper_broker"],
        "risk_boundary": "No real-money order submission.",
    },
    {
        "id": "central_risk_engine",
        "name": "Central risk engine",
        "state": "enabled",
        "maturity": "operational",
        "reason": "Required fail-closed gate for order submission.",
        "dependencies": [],
        "risk_boundary": "Hard limits and kill switch are not agent-configurable.",
    },
    {
        "id": "kill_switch",
        "name": "Emergency kill switch",
        "state": "enabled",
        "maturity": "operational",
        "reason": "Engaged by default; configuration rejects attempts to disable it.",
        "dependencies": ["central_risk_engine"],
        "risk_boundary": "Must remain fail-closed; this inventory cannot change it.",
    },
    {
        "id": "persistent_paper_ledger",
        "name": "Persistent paper ledger",
        "state": "enabled",
        "maturity": "experimental",
        "reason": "SQLite-backed paper state, restart recovery, and ledger verification are implemented.",
        "dependencies": ["paper_execution"],
        "risk_boundary": "Paper records only; no live account connection.",
    },
    {
        "id": "research_lineage",
        "name": "Research lineage and reflections",
        "state": "experimental",
        "maturity": "experimental",
        "reason": "Persistent paper-ledger lineage is on main; execution-boundary sanitization and propagation are under review.",
        "dependencies": ["persistent_paper_ledger"],
        "risk_boundary": "Unknown provenance remains unknown; no self-promotion.",
    },
    {
        "id": "learning_memory",
        "name": "Learning memory and personality",
        "state": "experimental",
        "maturity": "experimental",
        "reason": "Preference memory and advisory learning components exist; bounded to descriptive assistance.",
        "dependencies": ["local_sqlite"],
        "risk_boundary": "Cannot change hard risk limits, execution mode, or broker permissions.",
    },
    {
        "id": "public_data_scraper",
        "name": "Public data collection",
        "state": "experimental",
        "maturity": "experimental",
        "reason": "Safe-fetch foundation and read-only collectors exist; broader source coverage remains incomplete.",
        "dependencies": ["source_policy_checks"],
        "risk_boundary": "Respect provider terms, robots rules, authentication, privacy, and rate limits.",
    },
    {
        "id": "deriv_adapter",
        "name": "Deriv broker adapter",
        "state": "disabled",
        "maturity": "planned",
        "reason": "Adapter constructor intentionally rejects use; deterministic simulation adapter is not implemented.",
        "dependencies": ["paper_execution", "mock_broker_contract_tests"],
        "risk_boundary": "No provider credentials or real account access.",
    },
    {
        "id": "mt5_adapter",
        "name": "MetaTrader 5 adapter",
        "state": "disabled",
        "maturity": "planned",
        "reason": "Adapter constructor intentionally rejects use; deterministic simulation adapter is not implemented.",
        "dependencies": ["paper_execution", "mock_broker_contract_tests"],
        "risk_boundary": "No provider credentials or real account access.",
    },
    {
        "id": "demo_live_execution",
        "name": "Demo/live execution",
        "state": "unavailable",
        "maturity": "not_supported",
        "reason": "Runtime configuration accepts paper mode only; demo/live adapters are unavailable.",
        "dependencies": ["independent_review", "elapsed_validation", "future_release_gate"],
        "risk_boundary": "No execution-mode switch is exposed.",
    },
)

def feature_state_inventory() -> dict:
    """Return a detached, JSON-serializable feature inventory snapshot."""
    return {
        "schema_version": 1,
        "read_only": True,
        "execution_mode": "paper_only",
        "features": deepcopy(list(_FEATURES)),
    }
