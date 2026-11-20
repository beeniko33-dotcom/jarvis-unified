"""Bounded, auditable learning from JAEO task feedback.

This module learns operational patterns from approved feedback records. It never
changes prompts, permissions, policies, source code, production configuration,
or trading behavior. Recommendations are proposals for human review only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


POLICY_VERSION = "jaeo-learning-v1"
ALLOWED_STATUSES = {"completed", "failed", "blocked"}
MAX_RECORDS = 500
MIN_SAMPLE_SIZE = 3


@dataclass(frozen=True)
class LearningReport:
    policy_version: str
    sample_size: int
    completed: int
    failed: int
    blocked: int
    success_rate: float
    recurring_errors: tuple[tuple[str, int], ...]
    recommendations: tuple[str, ...]
    requires_human_review: bool = True
    policy_changed: bool = False
    self_modification_enabled: bool = False


def build_learning_report(records: Iterable[dict[str, Any]]) -> LearningReport:
    """Summarize a bounded set of persisted feedback records into review proposals."""
    normalized: list[dict[str, Any]] = []
    for record in records:
        if len(normalized) >= MAX_RECORDS:
            break
        if not isinstance(record, dict):
            continue
        status = record.get("status")
        if status not in ALLOWED_STATUSES:
            continue
        errors = record.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        safe_errors = [
            item.strip()[:240] for item in errors
            if isinstance(item, str) and item.strip()
        ][:20]
        normalized.append({"status": status, "errors": safe_errors})

    counts = Counter(item["status"] for item in normalized)
    completed = counts["completed"]
    failed = counts["failed"]
    blocked = counts["blocked"]
    sample_size = len(normalized)
    success_rate = round(completed / sample_size, 4) if sample_size else 0.0
    error_counts = Counter(
        error for item in normalized for error in item["errors"]
    )
    recurring = tuple(error_counts.most_common(10))

    recommendations: list[str] = []
    if sample_size < MIN_SAMPLE_SIZE:
        recommendations.append(
            "Collect at least three completed/failed/blocked task reports before drawing operational conclusions."
        )
    if failed:
        recommendations.append(
            "Review recurring failure causes and add regression tests before repeating affected tasks."
        )
    if blocked:
        recommendations.append(
            "Review approval and integration blockers; do not bypass gates to improve completion rate."
        )
    if recurring:
        recommendations.append(
            "Prioritize the most frequent sanitized error patterns for a human-reviewed engineering proposal."
        )
    if sample_size >= MIN_SAMPLE_SIZE and success_rate < 0.8:
        recommendations.append(
            "Escalate the workflow for human review; do not automatically relax policy or retry limits."
        )
    if not recommendations:
        recommendations.append(
            "No change is justified by this sample; continue collecting evidence."
        )

    return LearningReport(
        policy_version=POLICY_VERSION,
        sample_size=sample_size,
        completed=completed,
        failed=failed,
        blocked=blocked,
        success_rate=success_rate,
        recurring_errors=recurring,
        recommendations=tuple(recommendations),
    )


def report_as_dict(report: LearningReport) -> dict[str, Any]:
    """Return a JSON-serializable, dashboard/report-friendly representation."""
    return {
        "policy_version": report.policy_version,
        "sample_size": report.sample_size,
        "completed": report.completed,
        "failed": report.failed,
        "blocked": report.blocked,
        "success_rate": report.success_rate,
        "recurring_errors": [
            {"pattern": pattern, "count": count}
            for pattern, count in report.recurring_errors
        ],
        "recommendations": list(report.recommendations),
        "requires_human_review": report.requires_human_review,
        "policy_changed": report.policy_changed,
        "self_modification_enabled": report.self_modification_enabled,
        "mode": "paper",
        "live_trading_enabled": False,
    }
