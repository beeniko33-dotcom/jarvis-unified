"""Persistent, explainable recommendations that never control execution."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import Decimal
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from research.paper_outcomes import PaperOutcomeReport


_OWNER_DECISIONS = {
    "accepted_for_manual_review",
    "declined",
    "needs_more_evidence",
}


@dataclass(frozen=True)
class ShadowCandidate:
    candidate_id: str
    category: str
    title: str
    recommendation: str
    evidence: dict[str, Any]
    sample_size: int
    confidence: str
    status: str
    created_at: str
    review_due_at: str
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ShadowCandidateStore:
    """Append-only candidate and owner-review history, separate from execution."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shadow_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    confidence TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    review_due_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shadow_candidate_reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL REFERENCES shadow_candidates(candidate_id),
                    decision TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_shadow_reviews_candidate
                    ON shadow_candidate_reviews(candidate_id,review_id);
            """)
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def put(self, candidate: ShadowCandidate) -> bool:
        with closing(self._connect()) as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO shadow_candidates VALUES
                (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    candidate.candidate_id, candidate.category, candidate.title,
                    candidate.recommendation,
                    json.dumps(candidate.evidence, sort_keys=True, separators=(",", ":")),
                    candidate.sample_size, candidate.confidence, candidate.status,
                    candidate.created_at, candidate.review_due_at, candidate.expires_at,
                ),
            )
            db.commit()
            return cursor.rowcount == 1

    def list_candidates(
        self, *, include_expired: bool = False, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("candidate listing time must be timezone-aware")
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM shadow_candidates ORDER BY created_at,candidate_id"
            ).fetchall()
            reviews = db.execute(
                """SELECT candidate_id,decision,notes,reviewed_at
                FROM shadow_candidate_reviews ORDER BY review_id"""
            ).fetchall()
        review_map: dict[str, list[dict[str, str]]] = {}
        for candidate_id, decision, notes, reviewed_at in reviews:
            review_map.setdefault(candidate_id, []).append({
                "decision": decision, "notes": notes, "reviewed_at": reviewed_at,
            })
        result = []
        for row in rows:
            candidate = {
                "candidate_id": row[0], "category": row[1], "title": row[2],
                "recommendation": row[3], "evidence": json.loads(row[4]),
                "sample_size": row[5], "confidence": row[6], "status": row[7],
                "created_at": row[8], "review_due_at": row[9], "expires_at": row[10],
                "owner_reviews": review_map.get(row[0], []),
            }
            expired = current.astimezone(timezone.utc) >= datetime.fromisoformat(
                row[10].replace("Z", "+00:00")
            )
            candidate["expired"] = expired
            if include_expired or not expired:
                result.append(candidate)
        return result

    def record_owner_decision(
        self,
        candidate_id: str,
        decision: str,
        *,
        notes: str = "",
        reviewed_at: datetime | None = None,
    ) -> None:
        if decision not in _OWNER_DECISIONS:
            raise ValueError("decision must be a review-only owner decision")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise ValueError("notes must be text of at most 4000 characters")
        when = reviewed_at or datetime.now(timezone.utc)
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("review timestamp must be timezone-aware")
        with closing(self._connect()) as db:
            exists = db.execute(
                "SELECT 1 FROM shadow_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if exists is None:
                raise KeyError("shadow candidate does not exist")
            db.execute(
                """INSERT INTO shadow_candidate_reviews
                (candidate_id,decision,notes,reviewed_at) VALUES(?,?,?,?)""",
                (candidate_id, decision, notes, when.astimezone(timezone.utc).isoformat()),
            )
            db.commit()


def _candidate(
    *,
    category: str,
    title: str,
    recommendation: str,
    evidence: dict[str, Any],
    sample_size: int,
    now: datetime,
) -> ShadowCandidate:
    canonical = json.dumps(
        {"category": category, "evidence": evidence},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    candidate_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    confidence = "moderate" if sample_size >= 10 else "low"
    return ShadowCandidate(
        candidate_id=candidate_id,
        category=category,
        title=title,
        recommendation=recommendation,
        evidence=evidence,
        sample_size=sample_size,
        confidence=confidence,
        status="pending_owner_review",
        created_at=now.isoformat(),
        review_due_at=(now + timedelta(days=14)).isoformat(),
        expires_at=(now + timedelta(days=45)).isoformat(),
    )


def generate_shadow_candidates(
    report: PaperOutcomeReport,
    store: ShadowCandidateStore,
    *,
    now: datetime | None = None,
) -> list[ShadowCandidate]:
    """Create evidence-linked review suggestions; never alter a strategy or risk gate."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("candidate generation time must be timezone-aware")
    current = current.astimezone(timezone.utc)
    candidates: list[ShadowCandidate] = []
    source_ids = list(report.source_ledger_ids)

    if report.imported_ledger_events == 0:
        candidates.append(_candidate(
            category="data_coverage",
            title="Collect authentic paper-ledger observations",
            recommendation=(
                "Import a verified persistent paper ledger before drawing performance "
                "conclusions. Decision-only records are not trade-outcome evidence."
            ),
            evidence={
                "journal_events": report.journal_events,
                "imported_ledger_events": 0,
                "source_ledger_ids": source_ids,
            },
            sample_size=report.journal_events,
            now=current,
        ))

    if report.close_events > 0 and Decimal(report.net_realized_after_commission) < 0:
        candidates.append(_candidate(
            category="negative_net_outcome",
            title="Review realized losses and transaction costs",
            recommendation=(
                "Inspect the recorded close events, realized losses and commissions. "
                "Do not change parameters or relax risk limits automatically."
            ),
            evidence={
                "close_events": report.close_events,
                "gross_realized_pnl": report.gross_realized_pnl,
                "commission_paid": report.commission_paid,
                "net_realized_after_commission": report.net_realized_after_commission,
                "source_ledger_ids": source_ids,
            },
            sample_size=report.close_events,
            now=current,
        ))

    if report.partial_orders > 0:
        candidates.append(_candidate(
            category="partial_fill_review",
            title="Review partial-fill handling",
            recommendation=(
                "Inspect partial-fill sequences, remaining quantities and recorded fill IDs. "
                "Do not substitute assumed fills or synthetic liquidity."
            ),
            evidence={
                "partial_orders": report.partial_orders,
                "unique_fill_ids": report.unique_fill_ids,
                "source_ledger_ids": source_ids,
            },
            sample_size=report.unique_fill_ids,
            now=current,
        ))

    if report.rejected_decisions + report.reservation_rejections > 0:
        candidates.append(_candidate(
            category="rejection_review",
            title="Review rejected signals upstream",
            recommendation=(
                "Review rejection reasons and signal quality upstream. Preserve the central "
                "risk limits, kill switch and reservation checks; do not bypass them."
            ),
            evidence={
                "risk_rejections": report.rejected_decisions,
                "reservation_rejections": report.reservation_rejections,
            },
            sample_size=report.rejected_decisions + report.reservation_rejections,
            now=current,
        ))

    if report.missing_drawdown_observations > 0:
        candidates.append(_candidate(
            category="mark_coverage",
            title="Improve account mark coverage",
            recommendation=(
                "Review missing mark and account snapshots before relying on drawdown "
                "comparisons. Keep missing values explicitly unknown."
            ),
            evidence={
                "missing_drawdown_observations": report.missing_drawdown_observations,
                "drawdown_observations": report.drawdown_observations,
            },
            sample_size=report.drawdown_observations + report.missing_drawdown_observations,
            now=current,
        ))

    if report.max_observed_drawdown_pct is not None and Decimal(
        report.max_observed_drawdown_pct
    ) > 0:
        candidates.append(_candidate(
            category="drawdown_review",
            title="Review observed drawdown path",
            recommendation=(
                "Inspect the sequence of equity and mark observations around the recorded "
                "drawdown. This is a review prompt, not a proposal to loosen safeguards."
            ),
            evidence={
                "max_observed_drawdown_pct": report.max_observed_drawdown_pct,
                "drawdown_observations": report.drawdown_observations,
                "source_ledger_ids": source_ids,
            },
            sample_size=report.drawdown_observations,
            now=current,
        ))

    for candidate in candidates:
        store.put(candidate)
    return candidates
