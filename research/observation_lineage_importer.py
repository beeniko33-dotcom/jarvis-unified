"""Read-only bridge from execution observations into typed research lineage."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from research.event_lineage import ResearchEvent, ResearchEventLedger, ResearchStage
from research.execution_observations import ExecutionObservationJournal


class ObservationLineageImportError(RuntimeError):
    """Source or destination integrity failed during lineage import."""


@dataclass(frozen=True)
class ObservationLineageImportReport:
    imported: int
    already_present: int
    source_events_seen: int
    source_hash_chain_valid: bool
    lineage_hash_chain_valid: bool
    provider_authenticity_verified: int
    evidence_eligible: bool
    status: str


def import_execution_observations(
    source: ExecutionObservationJournal,
    destination: ResearchEventLedger,
    *,
    page_size: int = 500,
) -> ObservationLineageImportReport:
    """Idempotently copy source observations as root OBSERVATION events.

    No feature, forecast, decision, or outcome nodes are synthesized. Those
    stages must be emitted by their respective producers.
    """
    if not isinstance(source, ExecutionObservationJournal):
        raise TypeError("source must be an ExecutionObservationJournal")
    if not isinstance(destination, ResearchEventLedger):
        raise TypeError("destination must be a ResearchEventLedger")
    if not isinstance(page_size, int) or not 1 <= page_size <= 10000:
        raise ValueError("page_size must be between 1 and 10000")
    if not source.verify():
        raise ObservationLineageImportError("source observation journal hash chain is invalid")
    before = destination.report()["events"]
    if not destination.verify():
        raise ObservationLineageImportError("destination research lineage hash chain is invalid")

    seen = 0
    cursor = 0
    while True:
        page = source.list_events(limit=page_size, after_seq=cursor)
        if not page:
            break
        for item in page:
            seen += 1
            payload: dict[str, Any] = {
                "source_event_id": item["event_id"],
                "source_event_type": item["event_type"],
                "source_sequence": item["seq"],
                "source_schema_version": item["schema_version"],
                "source_event_hash": item["event_hash"],
                "source_integrity_scope": "local_hash_chain_only",
                "evidence_class": "paper_execution_observation",
                "data": item["data"],
            }
            destination.append(ResearchEvent(
                event_id=f"execution-observation:{item['event_id']}",
                stage=ResearchStage.OBSERVATION,
                occurred_at=datetime.fromisoformat(item["occurred_at"]),
                payload=payload,
                source_ref="execution_observation_journal:local_integrity_only",
            ))
        cursor = page[-1]["seq"]
        if len(page) < page_size:
            break

    source_valid = source.verify()
    lineage_valid = destination.verify()
    if not source_valid or not lineage_valid:
        raise ObservationLineageImportError("integrity changed or failed during lineage import")
    imported = destination.report()["events"] - before
    return ObservationLineageImportReport(
        imported=imported,
        already_present=seen - imported,
        source_events_seen=seen,
        source_hash_chain_valid=source_valid,
        lineage_hash_chain_valid=lineage_valid,
        provider_authenticity_verified=0,
        evidence_eligible=False,
        status="RESEARCH_ONLY",
    )
