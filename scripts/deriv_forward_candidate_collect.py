"""Run a bounded, read-only Deriv candidate collection and emit an honest report.

This job records unverified candidates only. It never authenticates a trading account,
submits orders, or awards forward-validation evidence credit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.deriv_feed import collect


def run(duration_seconds: int, database: Path, timeout_seconds: int) -> tuple[dict, int]:
    report = collect(duration_seconds, database, timeout_seconds)
    count = int(report.get("observation_count", 0))
    verified = int(report.get("verified_observation_count", 0))
    candidates = int(report.get("unverified_candidate_count", 0))
    safe = (
        report.get("event_chain_valid") is True
        and count > 0
        and candidates == count
        and verified == 0
        and report.get("level_3_forward_evidence_gate") == "BLOCKED_PROVENANCE"
        and report.get("level_3_certification") is False
        and report.get("trading_actions") == 0
        and report.get("account_authentication_used") is False
    )
    report.update({
        "candidate_collection_status": "PASS" if safe else "NO_QUALIFYING_CANDIDATE_DATA",
        "candidate_collection_only": True,
        "provider_provenance_verified": False,
        "forward_validation_credit_awarded": False,
        "live_trading_enabled": False,
    })
    return report, 0 if safe else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--db", type=Path, default=Path("var/deriv_eurusd_forward.sqlite3"))
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.timeout_seconds < 1:
        parser.error("duration and timeout must be positive")
    report, status = run(args.duration_seconds, args.db, args.timeout_seconds)
    print(json.dumps(report, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
