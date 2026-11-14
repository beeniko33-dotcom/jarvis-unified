"""Repeatable SQLite online-backup and restore drill for the paper ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from brokers.paper.persistent import PersistentPaperBroker


def _integrity(path: Path) -> str:
    with closing(sqlite3.connect(path)) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {path}: {result}")
        foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"foreign-key check failed for {path}: {foreign_key_errors[:5]}")
    return result


def _table_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as db:
        names = [
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {}
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            counts[name] = int(db.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
        return counts


def _online_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source, timeout=30)) as source_db:
        with closing(sqlite3.connect(destination, timeout=30)) as destination_db:
            source_db.backup(destination_db, pages=256, sleep=0.05)
            destination_db.commit()


def _verify_paper_chain(path: Path) -> dict:
    # Constructor restores the snapshot and verifies every hash-chain link and
    # the snapshot-to-audit-tail match. A failure locks the drill closed.
    broker = PersistentPaperBroker(database_path=path)
    with closing(broker._connect()) as db:
        broker._verify_chain(db)
        state = db.execute(
            "SELECT payload FROM paper_state WHERE singleton=1"
        ).fetchone()
        events = db.execute("SELECT COUNT(*) FROM paper_events").fetchone()[0]
        tail = db.execute(
            "SELECT event_hash FROM paper_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
    if state is None or tail is None:
        raise RuntimeError(f"paper ledger is missing its snapshot or audit tail: {path}")
    return {"event_count": int(events), "tail_hash": tail[0]}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_restore_drill(
    source: str | Path,
    backup: str | Path,
    restored: str | Path,
) -> dict:
    source, backup, restored = map(lambda item: Path(item).resolve(), (source, backup, restored))
    if len({source, backup, restored}) != 3:
        raise ValueError("source, backup and restored database paths must all be different")
    if not source.is_file():
        raise FileNotFoundError(f"source paper ledger does not exist: {source}")
    if backup.exists() or restored.exists():
        raise FileExistsError("backup and restored destinations must not already exist")

    source_integrity = _integrity(source)
    source_chain = _verify_paper_chain(source)
    source_counts = _table_counts(source)

    _online_backup(source, backup)
    backup_integrity = _integrity(backup)
    backup_chain = _verify_paper_chain(backup)
    backup_counts = _table_counts(backup)

    _online_backup(backup, restored)
    restored_integrity = _integrity(restored)
    restored_chain = _verify_paper_chain(restored)
    restored_counts = _table_counts(restored)

    if source_counts != backup_counts or source_counts != restored_counts:
        raise RuntimeError("table record counts changed during backup/restore")
    if source_chain != backup_chain or source_chain != restored_chain:
        raise RuntimeError("paper event-chain tail or event count changed during backup/restore")

    return {
        "ok": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "backup": str(backup),
        "restored": str(restored),
        "integrity": {
            "source": source_integrity,
            "backup": backup_integrity,
            "restored": restored_integrity,
        },
        "paper_event_chain": source_chain,
        "table_record_counts": source_counts,
        "sha256": {
            "backup": _sha256(backup),
            "restored": _sha256(restored),
        },
        "note": "Software backup/restore drill only; not market-data provenance or Level 3 evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Existing persistent paper-ledger SQLite database")
    parser.add_argument("--backup", type=Path, required=True, help="New backup destination (must not exist)")
    parser.add_argument("--restored", type=Path, required=True, help="New restore destination (must not exist)")
    args = parser.parse_args()
    result = backup_restore_drill(args.source, args.backup, args.restored)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
