#!/usr/bin/env python3
"""Audit a persistent Jarvis paper account (SQLite) across its whole history.

Read-only against the account database; never connects to a broker. Exit codes: 0 verified with
nothing needing attention, 2 an integrity error or a warning that needs the operator.

--anchor-file is an append-only JSONL record of past chain heads. Keep it somewhere the account
database's host cannot edit (another machine, a repo, a write-once store): it is what makes a
completely rewritten history detectable. It is only ever appended to, and only after a clean audit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.persistent_account_audit import audit_account  # noqa: E402


def _load_anchors(path: Path) -> list[dict]:
    anchors = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"anchor file line {number} is not valid JSON: {exc}") from exc
        if not isinstance(item, dict) or "seq" not in item or "event_hash" not in item:
            raise ValueError(f"anchor file line {number} lacks seq/event_hash")
        anchors.append(item)
    return anchors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="persistent paper account SQLite file")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="UTC date (YYYY-MM-DD)")
    parser.add_argument("--anchor-file", type=Path, default=None, help="append-only JSONL of chain heads")
    args = parser.parse_args(argv)

    anchors: list[dict] = []
    if args.anchor_file is not None and args.anchor_file.is_file():
        try:
            anchors = _load_anchors(args.anchor_file)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        result = audit_account(args.database, as_of=args.as_of, anchors=anchors)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.anchor_file is not None and result["status"] == "verified":
        head = result["head"]
        known = {(a["seq"], a["event_hash"]) for a in anchors}
        if (head["seq"], head["event_hash"]) not in known:
            args.anchor_file.parent.mkdir(parents=True, exist_ok=True)
            with args.anchor_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "account_id": result["account_id"],
                    "seq": head["seq"],
                    "event_hash": head["event_hash"],
                }) + "\n")
            result["anchor_recorded"] = True
        else:
            result["anchor_recorded"] = False

    print(json.dumps(result, indent=2))
    needs_attention = result["status"] != "verified" or any(
        item["severity"] in {"error", "warning"} for item in result["findings"]
    )
    return 2 if needs_attention else 0


if __name__ == "__main__":
    raise SystemExit(main())
