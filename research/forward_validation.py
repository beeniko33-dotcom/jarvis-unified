"""Durable candidate store and conservative gate for forward paper observations.

The current implementation has no trusted provider verifier. Every observation is stored
as an unverified candidate. No caller-supplied callback, JSON field, CLI flag, or imported
record can enable evidence credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from core.sqlite_wal import enable_wal
from research.trading_calendar import TradingCalendar

REQUIRED = {
    "observed_at", "instrument", "provider", "source", "interval",
    "strategy_id", "strategy_version", "price",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_timestamp(value: str) -> tuple[str, str, datetime]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("observed_at must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("observed_at must be ISO-8601 with an explicit UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must include an explicit timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds"), utc.date().isoformat(), utc


def validate_observation(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ValueError("each observation must be a JSON object")
    missing = REQUIRED.difference(item)
    if missing:
        raise ValueError("missing required fields: " + ", ".join(sorted(missing)))
    ts, utc_day, parsed = normalize_timestamp(item["observed_at"])
    for field in ("instrument", "provider", "source", "interval", "strategy_id", "strategy_version"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise ValueError(field + " must be a non-empty string")
    try:
        price = Decimal(str(item["price"]))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("price must be a positive finite decimal") from exc
    if not price.is_finite() or price <= 0:
        raise ValueError("price must be a positive finite decimal")
    if item.get("evidence_type") not in (None, "forward_paper_observation"):
        raise ValueError("historical, synthetic, demo, and replay evidence is not accepted")
    normalized = dict(item)
    normalized["observed_at"] = ts
    normalized["utc_day"] = utc_day
    normalized["price"] = str(price)
    normalized.pop("evidence_type", None)
    normalized["_parsed_observed_at"] = parsed
    return normalized


class ForwardEvidenceStore:
    def __init__(
        self,
        database: Path,
        *,
        instrument: str,
        provider: str,
        interval: str,
        strategy_id: str,
        strategy_version: str,
        clock: Callable[[], datetime] = utc_now,
        max_observation_age: timedelta = timedelta(minutes=10),
        future_tolerance: timedelta = timedelta(minutes=1),
        calendar_path: Path | None = None,
    ):
        values = (instrument, provider, interval, strategy_id, strategy_version)
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError("instrument, provider, interval and strategy identity must be explicit")
        if max_observation_age <= timedelta(0) or future_tolerance < timedelta(0):
            raise ValueError("observation age must be positive and future tolerance non-negative")
        self.calendar = TradingCalendar.load(calendar_path) if calendar_path else TradingCalendar.load()
        self.config = {
            "instrument": instrument, "provider": provider, "interval": interval,
            "strategy_id": strategy_id, "strategy_version": strategy_version,
            "trading_calendar_version": self.calendar.version,
            "trading_calendar_sha256": self.calendar.sha256,
        }
        self.clock = clock
        self.max_observation_age = max_observation_age
        self.future_tolerance = future_tolerance
        database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database, timeout=30, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=30000")
        self._enable_wal(self.db)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT NOT NULL,
          ingested_at TEXT NOT NULL, utc_day TEXT NOT NULL, instrument TEXT NOT NULL,
          provider TEXT NOT NULL, source TEXT NOT NULL, interval TEXT NOT NULL,
          strategy_id TEXT NOT NULL, strategy_version TEXT NOT NULL, price TEXT NOT NULL,
          provenance_verified INTEGER NOT NULL, payload TEXT NOT NULL,
          previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE,
          UNIQUE(instrument, interval, observed_at));
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(observations)")}
        if "ingested_at" not in columns:
            self.db.close()
            raise ValueError("legacy evidence database lacks trusted ingestion timestamps; start a new database")
        legacy_verified = self.db.execute(
            "SELECT COUNT(*) FROM observations WHERE provenance_verified=1"
        ).fetchone()[0]
        if legacy_verified:
            self.db.close()
            raise ValueError(
                "database contains records approved by the legacy injectable verifier; "
                "preserve it for audit and start a new database with this fail-closed version"
            )
        encoded = json.dumps(self.config, sort_keys=True, separators=(",", ":"))
        existing = self.db.execute("SELECT value FROM metadata WHERE key='configuration'").fetchone()
        if existing and existing[0] != encoded:
            self.db.close()
            raise ValueError("database configuration mismatch; use a separate database per validation run")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('configuration', ?)", (encoded,))
        self.db.commit()

    @staticmethod
    def _enable_wal(db):
        enable_wal(db)

    def close(self):
        self.db.close()

    def ingest(self, observation: dict) -> bool:
        item = validate_observation(observation)
        observed = item.pop("_parsed_observed_at")
        for key in ("instrument", "provider", "interval", "strategy_id", "strategy_version"):
            expected = self.config[key]
            if item[key] != expected:
                raise ValueError(f"{key} mismatch: expected {expected!r}")
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("collector clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        age = now - observed
        if age < -self.future_tolerance:
            raise ValueError("observation timestamp is in the future")
        if age > self.max_observation_age:
            raise ValueError("stale/backfilled observation rejected; only fresh observations may be ingested")
        # Trust-bearing fields are controlled exclusively by this store. Strip any
        # caller-supplied flags before persisting the payload; a forged JSON boolean
        # must not survive as an apparently authoritative field.
        for trust_field in (
            "verified", "provenance_verified", "evidence_credit",
            "tls_verified", "evidence_class",
        ):
            item.pop(trust_field, None)
        # No trusted provider verifier is implemented yet. Never accept a public
        # callback here: arbitrary caller code could return True and mint evidence.
        verified = False
        item["ingested_at"] = now.isoformat(timespec="microseconds")
        item["provenance_verified"] = verified
        item["evidence_credit"] = False
        item["evidence_class"] = "unverified_candidate"
        payload = json.dumps(item, sort_keys=True, separators=(",", ":"))
        try:
            # Acquire the SQLite write reservation before reading the chain tail.
            # This serializes tail selection and append across independent processes.
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.db.execute(
                "SELECT record_hash FROM observations ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = previous[0] if previous else "GENESIS"
            digest = hashlib.sha256((prev_hash + "|" + payload).encode()).hexdigest()
            self.db.execute(
                """INSERT INTO observations(observed_at,ingested_at,utc_day,instrument,provider,
                source,interval,strategy_id,strategy_version,price,provenance_verified,payload,
                previous_hash,record_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["observed_at"], item["ingested_at"], item["utc_day"], item["instrument"],
                 item["provider"], item["source"], item["interval"], item["strategy_id"],
                 item["strategy_version"], item["price"], int(verified), payload, prev_hash, digest),
            )
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            if "UNIQUE constraint failed: observations.instrument, observations.interval, observations.observed_at" in str(exc):
                return False
            raise
        except Exception:
            self.db.rollback()
            raise
        return True

    def verify_chain(self) -> bool:
        previous = "GENESIS"
        rows = self.db.execute(
            "SELECT payload,previous_hash,record_hash FROM observations ORDER BY id"
        )
        for payload, prev_hash, record_hash in rows:
            expected = hashlib.sha256((previous + "|" + payload).encode()).hexdigest()
            if prev_hash != previous or record_hash != expected:
                return False
            previous = record_hash
        return True

    def report(self, required_days: int = 30, provisional_required_days: int = 2) -> dict:
        if required_days < 1 or provisional_required_days < 1:
            raise ValueError("required and provisional day thresholds must be at least 1")
        verified_timestamps = [row[0] for row in self.db.execute(
            "SELECT observed_at FROM observations WHERE provenance_verified=1 ORDER BY observed_at"
        )]
        candidate_timestamps = [row[0] for row in self.db.execute(
            "SELECT observed_at FROM observations WHERE provenance_verified=0 ORDER BY observed_at"
        )]
        days = sorted({datetime.fromisoformat(value).date().isoformat() for value in verified_timestamps})
        latest = days[-1] if days else None
        latest_verified = self.db.execute(
            "SELECT observed_at FROM observations WHERE provenance_verified=1 ORDER BY observed_at DESC LIMIT 1"
        ).fetchone()
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("collector clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        latest_age = now - datetime.fromisoformat(latest_verified[0]) if latest_verified else None
        latest_is_fresh = bool(
            latest_age is not None
            and -self.future_tolerance <= latest_age <= self.max_observation_age
        )
        streak, latest_completed_trading_day = self.calendar.consecutive_covered_days(
            verified_timestamps, now
        )
        candidate_day = self.calendar.latest_completed_trading_day(now)
        candidate_coverage = self.calendar.daily_coverage(candidate_timestamps, candidate_day)
        valid_chain = self.verify_chain()
        total = self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        verified_count = self.db.execute(
            "SELECT COUNT(*) FROM observations WHERE provenance_verified=1"
        ).fetchone()[0]
        unverified_count = total - verified_count
        if not valid_chain:
            gate = "BLOCKED_CHAIN"
            provisional_gate = "BLOCKED_CHAIN"
        elif not verified_count:
            gate = "BLOCKED_PROVENANCE"
            provisional_gate = "BLOCKED_PROVENANCE"
        elif not latest_is_fresh:
            gate = "BLOCKED_STALE"
            provisional_gate = "BLOCKED_STALE"
        else:
            gate = "PASS" if streak >= required_days else "NOT_MET"
            provisional_gate = (
                "PROVISIONAL_PASS" if streak >= provisional_required_days else "NOT_MET"
            )
        return {
            "evidence_class": "provider_verified_forward_paper_candidates_only",
            "configuration": self.config,
            "observation_count": total,
            "verified_observation_count": verified_count,
            "unverified_candidate_count": unverified_count,
            "distinct_verified_utc_days": len(days),
            "first_verified_utc_day": days[0] if days else None,
            "latest_verified_utc_day": latest,
            "latest_consecutive_verified_trading_days_streak": streak,
            "required_consecutive_trading_days": required_days,
            "provisional_assessment_required_consecutive_trading_days": provisional_required_days,
            "provisional_assessment_gate": provisional_gate,
            "provisional_assessment_ready": provisional_gate == "PROVISIONAL_PASS",
            "provisional_assessment_is_level_3_certification": False,
            "latest_completed_expected_trading_day": latest_completed_trading_day,
            "trading_calendar_version": self.calendar.version,
            "trading_calendar_sha256": self.calendar.sha256,
            "daily_candidate_coverage": candidate_coverage,
            "daily_candidate_coverage_is_verified": False,
            "stale_observations_rejected": True,
            "ingestion_time_is_collector_generated": True,
            "provider_signature_or_equivalent_verifier_configured": False,
            "missing_expected_trading_days_break_streak": True,
            "non_trading_days_are_neutral_only_when_calendar_says_so": True,
            "daily_coverage_requires_all_two_hourly_buckets": True,
            "latest_verified_observation_age_seconds": latest_age.total_seconds() if latest_age is not None else None,
            "latest_verified_observation_fresh": latest_is_fresh,
            "maximum_verified_observation_age_seconds": self.max_observation_age.total_seconds(),
            "event_chain_valid": valid_chain,
            "level_3_forward_evidence_gate": gate,
            "level_3_certification": False,
            "note": "A calendar coverage pass is necessary, not sufficient, for Level 3 certification. Current collectors store only unverified candidates; candidate coverage never earns verified-day credit. The provider verifier must be independently audited.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="Fresh externally collected JSONL observations")
    parser.add_argument("--db", type=Path, default=Path("var/forward_validation.sqlite3"))
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument("--required-days", type=int, default=30,
                        help="Full Level 3 consecutive trading-day requirement (default: 30)")
    parser.add_argument("--provisional-days", type=int, default=2,
                        help="Non-certifying provisional assessment threshold (default: 2)")
    args = parser.parse_args()
    store = ForwardEvidenceStore(
        args.db, instrument=args.instrument, provider=args.provider, interval=args.interval,
        strategy_id=args.strategy_id, strategy_version=args.strategy_version,
    )
    try:
        accepted = duplicates = 0
        with args.jsonl.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    inserted = store.ingest(json.loads(line))
                except (ValueError, json.JSONDecodeError) as exc:
                    parser.error(f"line {line_no}: {exc}")
                accepted += int(inserted)
                duplicates += int(not inserted)
        result = store.report(args.required_days, args.provisional_days)
        result["new_observations_ingested"] = accepted
        result["duplicate_observations_ignored"] = duplicates
        print(json.dumps(result, indent=2))
        return 0 if result["level_3_forward_evidence_gate"] == "PASS" else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
