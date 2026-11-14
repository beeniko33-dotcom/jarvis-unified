"""Idempotent bridge from journal observations to factual paper-session reflections.

The bridge reads a verified learning journal only. It never writes to the broker
ledger, infers missing market-data provenance, or treats paper observations as
provider-authenticated evidence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from research.execution_observations import ExecutionObservationJournal
from research.reflection import ReflectionStore, SessionEvent, SessionReflection


class PaperReflectionBridgeError(RuntimeError):
    """The source learning journal cannot safely produce reflections."""


def _utc_day(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise PaperReflectionBridgeError("journal event has an invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperReflectionBridgeError("journal event timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc).date().isoformat()


def _summary(event_type: str, data: dict[str, Any]) -> str:
    """Render only fields actually present; nulls remain explicitly unknown."""
    source_type = data.get("source_event_type")
    label = f"paper ledger {source_type}" if event_type == "paper_ledger_event" else event_type
    fields = (
        "symbol", "side", "quantity", "filled_quantity", "remaining_quantity",
        "result_status", "status", "reason", "risk_reason", "order_id",
        "client_order_id", "realized_delta", "commission_delta",
        "source_event_seq", "source_utc_day",
    )
    facts = []
    for key in fields:
        if key in data:
            value = data[key]
            facts.append(f"{key}={value if value is not None else 'unknown'}")
    if event_type == "paper_ledger_event":
        for key in ("realized_delta", "commission_delta"):
            if key not in data:
                facts.append(f"{key}=unknown")
    suffix = "; ".join(facts) if facts else "no additional fields recorded"
    return f"Recorded {label}; {suffix}"


def _session_identity(event: dict[str, Any], day: str) -> str:
    data = event["data"]
    source_id = data.get("source_ledger_id")
    if source_id:
        return f"paper-ledger:{source_id}:{day}"
    explicit = data.get("session_id")
    if isinstance(explicit, str) and explicit.strip():
        return f"paper-execution:{explicit.strip()}:{day}"
    return f"paper-execution:{day}"


def build_paper_reflections(
    journal: ExecutionObservationJournal,
    store: ReflectionStore,
) -> list[SessionReflection]:
    """Create one deterministic reflection per source/day from every journal event."""
    if not journal.verify():
        raise PaperReflectionBridgeError("learning journal hash chain is invalid")

    events: list[dict[str, Any]] = []
    cursor = 0
    while True:
        page = journal.list_events(limit=1000, after_seq=cursor)
        if not page:
            break
        events.extend(page)
        cursor = page[-1]["seq"]
        if len(page) < 1000:
            break

    if not journal.verify():
        raise PaperReflectionBridgeError(
            "learning journal changed or became invalid during reflection generation"
        )

    groups: dict[str, list[SessionEvent]] = defaultdict(list)
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            raise PaperReflectionBridgeError("journal event data must be an object")
        occurred_at = event.get("occurred_at")
        if event["event_type"] == "paper_ledger_event":
            occurred_at = data.get("source_created_at", occurred_at)
        day = _utc_day(occurred_at)
        session_id = _session_identity(event, day)
        source_ref = f"learning-journal:{event['event_id']}:{event['event_hash']}"
        groups[session_id].append(SessionEvent(
            event_id=str(event["event_id"]),
            occurred_at=occurred_at,
            event_type=str(event["event_type"]),
            summary=_summary(str(event["event_type"]), data),
            source_ref=source_ref,
            # Journal integrity verifies the local record, not the authenticity
            # of the underlying market-data provider.
            provenance="not_applicable",
        ))

    reflections = []
    for session_id in sorted(groups):
        reflections.append(store.build(
            session_id=session_id,
            events=groups[session_id],
            unknowns=[
                "Market-data provider authenticity is not established by this local journal.",
                "Causal strategy performance and per-entry P&L attribution are not inferred.",
                "Missing strategy, configuration and experiment links remain unknown.",
            ],
            next_low_risk_steps=[
                "Review each cited source event and reconcile it with the original paper ledger.",
                "Check missing signal, strategy and experiment lineage before comparing outcomes.",
            ],
        ))
    return reflections
