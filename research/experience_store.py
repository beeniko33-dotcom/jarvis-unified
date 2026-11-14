"""Versioned research experiment registry with immutable provenance metadata.

This registry records experiments and their reported outcomes. It does not execute
strategies, certify data, or authorize changes to paper/live execution.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ALLOWED_DATA_STATUSES = {"historical", "synthetic", "unverified_candidate", "verified"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _required(value: str, field: str, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{field} must be a non-empty string of at most {limit} chars")
    return value.strip()



def _reject_sensitive_config_keys(value: Any, path: str = "config") -> None:
    """Keep credentials and wallet material out of local experiment snapshots."""
    forbidden = (
        "password", "secret", "token", "api_key", "apikey", "private_key",
        "credential", "wallet_seed", "mnemonic",
    )
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in forbidden):
                raise ValueError(f"sensitive config key is not allowed at {path}.{key}")
            _reject_sensitive_config_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_config_keys(item, f"{path}[{index}]")


def _canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    name: str
    hypothesis: str
    strategy_version: str
    config_hash: str
    dataset_id: str
    dataset_hash: str
    data_status: str
    start_at: str
    end_at: str
    created_at: str
    metrics: dict[str, Any]
    metrics_hash: str
    schema_version: int = 2
    source_ledger_hash: str | None = None
    source_journal_hash: str | None = None
    evidence_status: str = "metadata_only"


class ExperienceStore:
    """Append-only experiment metadata and outcome registry."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    data_status TEXT NOT NULL CHECK(data_status IN
                        ('historical','synthetic','unverified_candidate','verified')),
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    metrics_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experiments_created
                    ON research_experiments(created_at);
                CREATE INDEX IF NOT EXISTS idx_experiments_dataset
                    ON research_experiments(dataset_id,dataset_hash);
            """)
            columns = {
                row["name"] for row in db.execute(
                    "PRAGMA table_info(research_experiments)"
                ).fetchall()
            }
            migrations = {
                "config_json": "TEXT",
                "schema_version": "INTEGER NOT NULL DEFAULT 1",
                "source_ledger_hash": "TEXT",
                "source_journal_hash": "TEXT",
                "evidence_status": "TEXT NOT NULL DEFAULT 'metadata_only'",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    db.execute(
                        f"ALTER TABLE research_experiments ADD COLUMN {column} {definition}"
                    )
            db.executescript("""
                CREATE TABLE IF NOT EXISTS experiment_source_verifications (
                    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL REFERENCES research_experiments(experiment_id),
                    ledger_hash TEXT NOT NULL,
                    journal_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('verified','mismatch')),
                    checked_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_source_verifications
                    ON experiment_source_verifications(experiment_id,verification_id);
            """)
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def record(
        self, *, name: str, hypothesis: str, strategy_version: str,
        config: dict[str, Any], dataset_id: str, dataset_hash: str,
        data_status: str, start_at: str, end_at: str,
        metrics: dict[str, Any],
        source_ledger_hash: str | None = None,
        source_journal_hash: str | None = None,
    ) -> Experiment:
        name = _required(name, "name")
        hypothesis = _required(hypothesis, "hypothesis", 4000)
        strategy_version = _required(strategy_version, "strategy_version")
        dataset_id = _required(dataset_id, "dataset_id")
        dataset_hash = _required(dataset_hash, "dataset_hash", 256)
        if data_status not in _ALLOWED_DATA_STATUSES:
            raise ValueError(f"data_status must be one of {sorted(_ALLOWED_DATA_STATUSES)}")
        start_at, end_at = _timestamp(start_at, "start_at"), _timestamp(end_at, "end_at")
        if start_at >= end_at:
            raise ValueError("start_at must be earlier than end_at")
        if not isinstance(config, dict) or not isinstance(metrics, dict):
            raise ValueError("config and metrics must be JSON objects")
        _reject_sensitive_config_keys(config)
        config_json = json.dumps(
            config, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
        for value, field in (
            (source_ledger_hash, "source_ledger_hash"),
            (source_journal_hash, "source_journal_hash"),
        ):
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value.lower())
            ):
                raise ValueError(f"{field} must be a 64-character SHA-256 hex digest")
        source_ledger_hash = (
            source_ledger_hash.lower() if source_ledger_hash is not None else None
        )
        source_journal_hash = (
            source_journal_hash.lower() if source_journal_hash is not None else None
        )
        evidence_status = (
            "source_referenced_unverified"
            if source_ledger_hash or source_journal_hash
            else "metadata_only"
        )
        metrics_json = json.dumps(metrics, sort_keys=True, separators=(",", ":"), allow_nan=False)
        metrics_hash = hashlib.sha256(metrics_json.encode("utf-8")).hexdigest()
        item = Experiment(
            experiment_id=str(uuid.uuid4()), name=name, hypothesis=hypothesis,
            strategy_version=strategy_version, config_hash=config_hash,
            dataset_id=dataset_id, dataset_hash=dataset_hash, data_status=data_status,
            start_at=start_at, end_at=end_at, created_at=_now(),
            metrics=json.loads(metrics_json), metrics_hash=metrics_hash,
            schema_version=2, source_ledger_hash=source_ledger_hash,
            source_journal_hash=source_journal_hash, evidence_status=evidence_status,
        )
        with closing(self._connect()) as db:
            db.execute("""
                INSERT INTO research_experiments (
                    experiment_id,name,hypothesis,strategy_version,config_hash,
                    dataset_id,dataset_hash,data_status,start_at,end_at,created_at,
                    metrics_json,metrics_hash,config_json,schema_version,
                    source_ledger_hash,source_journal_hash,evidence_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item.experiment_id, item.name, item.hypothesis, item.strategy_version,
                item.config_hash, item.dataset_id, item.dataset_hash, item.data_status,
                item.start_at, item.end_at, item.created_at, metrics_json, item.metrics_hash,
                config_json, item.schema_version, item.source_ledger_hash,
                item.source_journal_hash, item.evidence_status,
            ))
            db.commit()
        return item

    def list(self, *, data_status: str | None = None) -> list[Experiment]:
        where = ""
        params: tuple[str, ...] = ()
        if data_status is not None:
            if data_status not in _ALLOWED_DATA_STATUSES:
                raise ValueError("unknown data_status")
            where = " WHERE e.data_status=?"
            params = (data_status,)
        with closing(self._connect()) as db:
            rows = db.execute(
                """SELECT e.*,
                    COALESCE((
                        SELECT v.status FROM experiment_source_verifications v
                        WHERE v.experiment_id=e.experiment_id
                        ORDER BY v.verification_id DESC LIMIT 1
                    ), e.evidence_status) AS current_evidence_status
                    FROM research_experiments e"""
                + where + " ORDER BY e.created_at,e.experiment_id",
                params,
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Experiment:
        values = dict(row)
        values["metrics"] = json.loads(values.pop("metrics_json"))
        values.pop("config_json", None)
        values["evidence_status"] = values.pop(
            "current_evidence_status", values.get("evidence_status", "metadata_only")
        )
        return Experiment(**values)

    @staticmethod
    def _file_sha256(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_source_artifacts(
        self, experiment_id: str, *, ledger_path: str | Path,
        journal_path: str | Path,
    ) -> dict[str, Any]:
        """Hash actual local artifacts and append a verification attempt.

        The paths are never persisted or returned. Only their SHA-256 digests and
        verification result are retained in the append-only verification history.
        """
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT source_ledger_hash,source_journal_hash
                FROM research_experiments WHERE experiment_id=?""",
                (experiment_id,),
            ).fetchone()
        if row is None:
            raise KeyError("experiment does not exist")
        ledger_hash = self._file_sha256(ledger_path)
        journal_hash = self._file_sha256(journal_path)
        matched = bool(
            row["source_ledger_hash"] and row["source_journal_hash"]
            and ledger_hash == row["source_ledger_hash"]
            and journal_hash == row["source_journal_hash"]
        )
        with closing(self._connect()) as db:
            db.execute(
                """INSERT INTO experiment_source_verifications
                (experiment_id,ledger_hash,journal_hash,status,checked_at)
                VALUES(?,?,?,?,?)""",
                (
                    experiment_id, ledger_hash, journal_hash,
                    "verified" if matched else "mismatch", _now(),
                ),
            )
            db.commit()
        return {
            "experiment_id": experiment_id,
            "status": "verified" if matched else "mismatch",
            "ledger_hash_matches": bool(row["source_ledger_hash"]) and
                ledger_hash == row["source_ledger_hash"],
            "journal_hash_matches": bool(row["source_journal_hash"]) and
                journal_hash == row["source_journal_hash"],
        }

    def verify(self, experiment_id: str) -> bool:
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT config_hash,config_json,metrics_json,metrics_hash
                FROM research_experiments WHERE experiment_id=?""",
                (experiment_id,),
            ).fetchone()
        if row is None:
            return False
        try:
            metrics = json.loads(row["metrics_json"])
            if row["config_json"] is None:
                return False
            config = json.loads(row["config_json"])
            return (
                isinstance(config, dict)
                and hashlib.sha256(row["config_json"].encode("utf-8")).hexdigest()
                == row["config_hash"]
                and hashlib.sha256(row["metrics_json"].encode("utf-8")).hexdigest()
                == row["metrics_hash"]
                and isinstance(metrics, dict)
            )
        except (TypeError, json.JSONDecodeError):
            return False


def chronological_split(
    timestamps: list[str], *, train_fraction: float = 0.6, validation_fraction: float = 0.2
) -> dict[str, list[int]]:
    """Return chronological index partitions; never randomly shuffle observations."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train + validation fractions must leave a test partition")
    parsed = [_timestamp(value, "timestamp") for value in timestamps]
    if parsed != sorted(parsed):
        raise ValueError("timestamps must be chronological and non-decreasing")
    n = len(parsed)
    train_end = int(n * train_fraction)
    validation_end = train_end + int(n * validation_fraction)
    if train_end < 1 or validation_end <= train_end or validation_end >= n:
        raise ValueError("not enough observations for requested chronological split")
    return {
        "train": list(range(0, train_end)),
        "validation": list(range(train_end, validation_end)),
        "test": list(range(validation_end, n)),
    }
