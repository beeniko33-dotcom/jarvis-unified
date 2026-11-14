"""Deterministic, read-only experiment comparison with strict evidence matching."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research.experience_store import Experiment, ExperienceStore


@dataclass(frozen=True)
class ExperimentComparison:
    left_experiment_id: str
    right_experiment_id: str
    comparable: bool
    reasons: tuple[str, ...]
    left_metrics: dict[str, Any]
    right_metrics: dict[str, Any]
    metric_deltas: dict[str, str]
    shared_dataset_hash: str | None
    shared_time_window: tuple[str, str] | None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        value["shared_time_window"] = (
            list(self.shared_time_window) if self.shared_time_window else None
        )
        return value


def compare_experiments(
    store: ExperienceStore, left_id: str, right_id: str
) -> ExperimentComparison:
    """Compare two immutable records; never rank incomparable or unverified evidence."""
    records = {item.experiment_id: item for item in store.list()}
    left = records.get(left_id)
    right = records.get(right_id)
    if left is None or right is None:
        raise KeyError("both experiment IDs must exist in the experience store")
    if left_id == right_id:
        raise ValueError("an experiment cannot be compared with itself")

    reasons: list[str] = []
    if not store.verify(left_id):
        reasons.append("left_experiment_integrity_failed")
    if not store.verify(right_id):
        reasons.append("right_experiment_integrity_failed")
    if left.dataset_id != right.dataset_id or left.dataset_hash != right.dataset_hash:
        reasons.append("dataset_identity_or_hash_mismatch")
    if left.data_status != "verified" or right.data_status != "verified":
        reasons.append("dataset_status_not_verified_for_both_experiments")
    if left.start_at != right.start_at or left.end_at != right.end_at:
        reasons.append("time_window_mismatch")
    if not left.source_ledger_hash or not right.source_ledger_hash:
        reasons.append("source_ledger_hash_missing")
    elif left.source_ledger_hash != right.source_ledger_hash:
        reasons.append("source_ledger_hash_mismatch")
    if not left.source_journal_hash or not right.source_journal_hash:
        reasons.append("source_journal_hash_missing")
    elif left.source_journal_hash != right.source_journal_hash:
        reasons.append("source_journal_hash_mismatch")
    if (
        left.evidence_status != "verified"
        or right.evidence_status != "verified"
    ):
        reasons.append("source_references_not_independently_verified")

    deltas: dict[str, str] = {}
    if not reasons:
        for key in sorted(set(left.metrics) & set(right.metrics)):
            a, b = left.metrics[key], right.metrics[key]
            if (
                isinstance(a, (int, float)) and not isinstance(a, bool)
                and isinstance(b, (int, float)) and not isinstance(b, bool)
            ):
                from decimal import Decimal, InvalidOperation

                try:
                    deltas[key] = str(Decimal(str(b)) - Decimal(str(a)))
                except (InvalidOperation, ValueError):
                    continue

    shared_dataset = (
        left.dataset_hash
        if left.dataset_id == right.dataset_id and left.dataset_hash == right.dataset_hash
        else None
    )
    shared_window = (
        (left.start_at, left.end_at)
        if left.start_at == right.start_at and left.end_at == right.end_at
        else None
    )
    return ExperimentComparison(
        left_experiment_id=left_id,
        right_experiment_id=right_id,
        comparable=not reasons,
        reasons=tuple(reasons),
        left_metrics=left.metrics,
        right_metrics=right.metrics,
        metric_deltas=deltas,
        shared_dataset_hash=shared_dataset,
        shared_time_window=shared_window,
    )
