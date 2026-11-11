#!/usr/bin/env python3
"""Local diagnostic for Jarvis Unified foundation.

Run from repo root:
  python scripts/diagnose.py

Checks structure, imports, config, risk defaults, and unit tests.
Does not enable live trading or load secrets.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


def check_structure() -> bool:
    section("Repository structure")
    required = [
        "main.py",
        "core/config.py",
        "core/models.py",
        "core/execution.py",
        "core/risk/engine.py",
        "core/portfolio/tracker.py",
        "core/signals/base.py",
        "brokers/base.py",
        "brokers/paper/broker.py",
        "brokers/deriv/adapter.py",
        "brokers/mt5/adapter.py",
        "apps/api/status.py",
        "apps/dashboard/index.html",
        "packages/scraper/safe_fetch.py",
        "scripts/paper_session.py",
        "scripts/paper_report.py",
        "tests/test_paper_report.py",
        "docs/LEVEL_3_RUNBOOK.md",
        "tests/test_config.py",
        "tests/test_risk_engine.py",
        "tests/test_paper_broker.py",
        "tests/test_execution.py",
        "tests/test_status_api.py",
        "tests/test_safe_fetch.py",
        ".github/workflows/ci.yml",
        "scripts/import_sources.sh",
        "docs/MATURITY.md",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    if missing:
        for path in missing:
            fail(f"missing {path}")
        return False
    ok(f"{len(required)} required foundation files present")
    sources = ROOT / "sources"
    imported = [p.name for p in sources.iterdir() if p.is_dir()] if sources.exists() else []
    if imported:
        ok(f"source imports present: {', '.join(sorted(imported))}")
    else:
        print("  [INFO] no source histories imported yet (run scripts/import_sources.sh locally)")
    return True


def check_imports() -> bool:
    section("Python imports")
    sys.path.insert(0, str(ROOT))
    modules = [
        "core.config",
        "core.models",
        "core.execution",
        "core.risk",
        "core.portfolio",
        "core.signals",
        "brokers.paper",
        "brokers.deriv",
        "brokers.mt5",
        "apps.api.status",
        "packages.scraper",
    ]
    all_ok = True
    for name in modules:
        try:
            importlib.import_module(name)
            ok(name)
        except Exception as exc:  # noqa: BLE001
            fail(f"{name}: {exc}")
            all_ok = False
    return all_ok


def check_config_and_risk() -> bool:
    section("Config + risk defaults")
    sys.path.insert(0, str(ROOT))
    from decimal import Decimal

    from core.config import Settings
    from core.models import OrderRequest, Side
    from core.risk import RiskEngine, RiskLimits

    env = {"JARVIS_MODE": "paper", "KILL_SWITCH": "true"}
    previous = {k: os.environ.get(k) for k in env}
    try:
        os.environ.update(env)
        settings = Settings.from_env()
        if settings.mode != "paper" or not settings.kill_switch:
            fail("paper mode / kill switch defaults incorrect")
            return False
        ok("Settings.from_env() paper + kill_switch")

        for bad_mode in ("live", "deriv_demo", "mt5_demo"):
            os.environ["JARVIS_MODE"] = bad_mode
            try:
                Settings.from_env()
                fail(f"accepted non-paper mode {bad_mode}")
                return False
            except ValueError:
                pass
        ok("non-paper modes rejected")

        os.environ["JARVIS_MODE"] = "paper"
        os.environ["KILL_SWITCH"] = "false"
        try:
            Settings.from_env()
            fail("allowed KILL_SWITCH=false via env")
            return False
        except ValueError:
            ok("KILL_SWITCH cannot be disabled via env")

        risk = RiskEngine(RiskLimits(Decimal("5"), Decimal("10"), 2, True))
        order = OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "diag")
        decision = risk.evaluate(order, daily_realized_pnl=Decimal("0"), open_positions=0)
        if decision.allowed:
            fail("kill switch did not block order")
            return False
        ok("kill switch blocks new entries by default")

        from brokers.deriv import DerivBroker
        from brokers.mt5 import MT5Broker

        for cls, name in ((DerivBroker, "Deriv"), (MT5Broker, "MT5")):
            try:
                cls()
                fail(f"{name} adapter constructed (should be disabled)")
                return False
            except RuntimeError:
                ok(f"{name} adapter construction blocked")
        return True
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def check_tests() -> bool:
    section("Unit tests")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail("unittest suite failed")
        print(result.stdout)
        print(result.stderr)
        return False
    lines = [line for line in result.stderr.splitlines() if " ... ok" in line or " ... FAIL" in line]
    ok(f"unittest discover passed ({len(lines)} cases reported)")
    return True


def check_entrypoint() -> bool:
    section("Entrypoint")
    result = subprocess.run(
        [sys.executable, "main.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "JARVIS_MODE": "paper", "KILL_SWITCH": "true"},
    )
    if result.returncode != 0:
        fail(f"main.py --check failed: {result.stderr or result.stdout}")
        return False
    ok("main.py --check succeeded")
    return True


def main() -> int:
    print("Jarvis Unified diagnostic")
    print(f"Root: {ROOT}")
    checks = [
        check_structure,
        check_imports,
        check_config_and_risk,
        check_tests,
        check_entrypoint,
    ]
    results = [fn() for fn in checks]
    section("Summary")
    if all(results):
        print("  Foundation checks passed locally.")
        print("  Level 2 still requires a green GitHub Actions run on main.")
        print("  History import still requires: bash scripts/import_sources.sh")
        print("  Paper session (Level 3 prep): python scripts/paper_session.py --allow-entries")
        print("  Paper metrics: python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30")
        return 0
    print("  One or more checks failed. Fix before claiming Level 2.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
