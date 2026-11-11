"""Append-only, provenance-aware store and UTC continuity gate for forward paper observations.

This module ingests externally collected observations. It does not fetch market data,
place orders, or treat historical replay/fixtures as forward evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED = {"observed_at", "instrument", "provider", "source", "interval",
            "strategy_id", "strategy_version", "price"}


def normalize_timestamp(value: str) -> tuple[str, str]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("observed_at must be ISO-8601 with an explicit UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must include an explicit timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds"), utc.date().isoformat()


def validate_observation(item: dict) -> dict:
    missing = REQUIRED.difference(item)
    if missing:
        raise ValueError("missing required fields: " + ", ".join(sorted(missing)))
    ts, utc_day = normalize_timestamp(item["observed_at"])
    for field in ("instrument", "provider", "source", "interval", "strategy_id", "strategy_version"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise ValueError(field + " must be a non-empty string")
    try:
        price = Decimal(str(item["price"]))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("price must be a positive finite decimal") from exc
    if not price.is_finite() or price <= 0:
        raise ValueError("price must be a positive finite decimal")
    normalized = dict(item)
    normalized["observed_at"] = ts
    normalized["utc_day"] = utc_day
    normalized["price"] = str(price)
    normalized["evidence_type"] = "forward_paper_observation"
    # Reject fields that would falsely promote the record's evidence class.
    if item.get("evidence_type") not in (None, "forward_paper_observation"):
        raise ValueError("only forward_paper_observation records are accepted")
    return normalized


class ForwardEvidenceStore:
    def __init__(self, database: Path, *, instrument: str, provider: str,
                 interval: str, strategy_id: str, strategy_version: str):
        values = (instrument, provider, interval, strategy_id, strategy_version)
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError("instrument, provider, interval and strategy identity must be explicit")
        self.config = {"instrument": instrument, "provider": provider, "interval": interval,
                       "strategy_id": strategy_id, "strategy_version": strategy_version}
        database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT NOT NULL,
          utc_day TEXT NOT NULL, instrument TEXT NOT NULL, provider TEXT NOT NULL,
          source TEXT NOT NULL, interval TEXT NOT NULL, strategy_id TEXT NOT NULL,
          strategy_version TEXT NOT NULL, price TEXT NOT NULL, payload TEXT NOT NULL,
          previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE,
          UNIQUE(instrument, interval, observed_at));
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        encoded = json.dumps(self.config, sort_keys=True, separators=(",", ":"))
        existing = self.db.execute("SELECT value FROM metadata WHERE key='configuration'").fetchone()
        if existing and existing[0] != encoded:
            raise ValueError("database configuration mismatch; use a separate database per validation run")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('configuration', ?)", (encoded,))
        self.db.commit()

    def close(self):
        self.db.close()

    def ingest(self, observation: dict) -> bool:
        item = validate_observation(observation)
        for key, expected in self.config.items():
            if item[key] != expected:
                raise ValueError(f"{key} mismatch: expected {expected!r}")
        previous = self.db.execute(
            "SELECT record_hash FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = previous[0] if previous else "GENESIS"
        payload = json.dumps(item, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((prev_hash + "|" + payload).encode()).hexdigest()
        try:
            with self.db:
                self.db.execute(
                    """INSERT INTO observations(observed_at,utc_day,instrument,provider,source,
                    interval,strategy_id,strategy_version,price,payload,previous_hash,record_hash)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["observed_at"], item["utc_day"], item["instrument"], item["provider"],
                     item["source"], item["interval"], item["strategy_id"], item["strategy_version"],
                     item["price"], payload, prev_hash, digest))
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: observations.instrument, observations.interval, observations.observed_at" in str(exc):
                return False
            raise
        return True

    def verify_chain(self) -> bool:
        previous = "GENESIS"
        rows = self.db.execute(
            "SELECT payload,previous_hash,record_hash FROM observations ORDER BY id")
        for payload, prev_hash, record_hash in rows:
            expected = hashlib.sha256((previous + "|" + payload).encode()).hexdigest()
            if prev_hash != previous or record_hash != expected:
                return False
            previous = record_hash
        return True

    def report(self, required_days: int = 30) -> dict:
        if required_days < 1:
            raise ValueError("required_days must be at least 1")
        days = [row[0] for row in self.db.execute(
            "SELECT DISTINCT utc_day FROM observations ORDER BY utc_day")]
        latest = days[-1] if days else None
        streak = 0
        expected = datetime.fromisoformat(latest).date() if latest else None
        for day in reversed(days):
            current = datetime.fromisoformat(day).date()
            if current != expected:
                break
            streak += 1
            expected = current - timedelta(days=1)
        valid_chain = self.verify_chain()
        count = self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        ready = bool(valid_chain and streak >= required_days)
        return {
            "evidence_class": "forward_paper_observations_only",
            "configuration": self.config,
            "observation_count": count,
            "distinct_utc_days": len(days),
            "first_utc_day": days[0] if days else None,
            "latest_utc_day": latest,
            "latest_consecutive_utc_day_streak": streak,
            "required_consecutive_utc_days": required_days,
            "missing_days_break_streak": True,
            "event_chain_valid": valid_chain,
            "level_3_forward_evidence_gate": "PASS" if ready else "NOT_MET",
            "level_3_certification": False,
            "note": "A 30-day coverage gate is necessary, not sufficient, for Level 3 certification. Independent review and risk/performance gates remain required."
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="Externally collected JSONL observations; no fixtures")
    parser.add_argument("--db", type=Path, default=Path("var/forward_validation.sqlite3"))
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument("--required-days", type=int, default=30)
    args = parser.parse_args()
    store = ForwardEvidenceStore(args.db, instrument=args.instrument, provider=args.provider,
        interval=args.interval, strategy_id=args.strategy_id, strategy_version=args.strategy_version)
    try:
        with args.jsonl.open(encoding="utf-8") as handle:
            accepted = duplicates = 0
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    inserted = store.ingest(json.loads(line))
                except (ValueError, json.JSONDecodeError) as exc:
                    parser.error(f"line {line_no}: {exc}")
                accepted += int(inserted)
                duplicates += int(not inserted)
        result = store.report(args.required_days)
        result["new_observations_ingested"] = accepted
        result["duplicate_observations_ignored"] = duplicates
        print(json.dumps(result, indent=2))
        return 0 if result["level_3_forward_evidence_gate"] == "PASS" else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
