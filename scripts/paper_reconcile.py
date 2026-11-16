#!/usr/bin/env python3
"""Replay a Jarvis paper JSONL ledger and check it against its own recorded balances.

Read-only; never connects to a broker. Exit codes: 0 reconciled, 2 discrepancies or incomplete.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.ledger_reconciliation import reconcile_ledger  # noqa: E402
from scripts.paper_report import load_rows  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?", default=Path("var/paper_ledger.jsonl"))
    args = parser.parse_args(argv)
    if not args.ledger.is_file():
        parser.error(f"ledger not found: {args.ledger}")
    try:
        result = reconcile_ledger(load_rows(args.ledger))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if result["status"] != "reconciled":
        print(f"NOT RECONCILED: status is {result['status']}.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
