"""Idempotent bridge from journal observations to factual paper-session reflections.

The bridge reads a verified learning journal only. It never writes to the broker
ledger, infers missing market-data provenance, or treats paper observations as
provider-authenticated evidence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
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


#: Fields whose value must be a hex digest. Anything else is not a hash.
_HASH_FIELDS = frozenset({
    "strategy_config_hash", "signal_context_hash", "data_hash",
})

#: Fields whose value must be a bounded identifier, never free text.
_IDENTIFIER_FIELDS = frozenset({
    "strategy_id", "strategy_version", "experiment_id", "signal_id",
    "signal_type", "data_source_id", "quote_source", "order_id",
    "client_order_id", "symbol", "side", "result_status", "status",
    "source_event_seq", "source_utc_day",
})

#: Fields that may legitimately be free text.
_FREE_TEXT_FIELDS = frozenset({"reason", "risk_reason"})

#: Substrings that mark a value as credential-shaped. A secret that reaches an
#: allowlisted *string* field is still a secret; the key allowlist cannot see it.
_CREDENTIAL_MARKERS = (
    "api_key", "apikey", "api-key", "secret", "password", "passwd", "token",
    "bearer", "authorization", "private_key", "privatekey", "access_key",
    "client_secret", "sk-", "sk_live", "sk_test", "ghp_", "xoxb-", "xoxp-",
    "-----begin", "aws_secret",
)

_HEX = frozenset("0123456789abcdefABCDEF")
_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:/"
)


def _looks_like_credential(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CREDENTIAL_MARKERS)


def _is_hex_digest(text: str) -> bool:
    """A hash is a hex digest of a plausible length (sha-1 .. sha-512)."""
    if not 8 <= len(text) <= 128:
        return False
    return all(char in _HEX for char in text)


def _is_identifier(text: str) -> bool:
    if not 1 <= len(text) <= 128:
        return False
    return all(char in _IDENTIFIER_CHARS for char in text)


def _render_lineage(key: str, value: Any) -> str:
    """Validate a lineage value against the contract for its own field.

    A single generic scalar check is not enough: a credential placed in an
    allowlisted *string* field would still be rendered. Each field therefore
    has its own format, and anything that does not satisfy it — including a
    credential-shaped string, a malformed hash or a non-finite number — is
    reported as ``unknown`` rather than echoed into the reflection.
    """
    if value is None:
        return "unknown"
    # Non-finite floats cannot be represented faithfully and are not lineage.
    if isinstance(value, float) and not math.isfinite(value):
        return "unknown"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return "unknown"

    text = value.strip()
    if not text:
        return "unknown"
    if _looks_like_credential(text):
        return "unknown"

    if key in _HASH_FIELDS:
        return text if _is_hex_digest(text) else "unknown"
    if key in _IDENTIFIER_FIELDS:
        return text if _is_identifier(text) else "unknown"
    if key in _FREE_TEXT_FIELDS:
        # Free text is allowed, but still bounded and never credential-shaped.
        return text if len(text) <= 500 else "unknown"
    # Unknown field: only a short, plain scalar is safe to echo.
    return text if len(text) <= 200 else "unknown"


def _summary(event_type: str, data: dict[str, Any]) -> str:
    """Render only fields actually present; nulls remain explicitly unknown."""
    source_type = data.get("source_event_type")
    label = f"paper ledger {source_type}" if event_type == "paper_ledger_event" else event_type
    fields = (
        "symbol", "side", "quantity", "filled_quantity", "remaining_quantity",
        "result_status", "status", "reason", "risk_reason", "order_id",
        "client_order_id", "realized_delta", "commission_delta",
        "source_event_seq", "source_utc_day", "strategy_id", "strategy_version",
        "strategy_config_hash", "experiment_id", "quote_source", "quote_timestamp",
        "signal_id", "signal_type", "signal_context_hash", "data_source_id",
        "data_hash",
    )
    facts = []
    metadata = data.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    for key in fields:
        if key in data:
            value = data[key]
        elif key in metadata:
            value = metadata[key]
        else:
            continue
        facts.append(f"{key}={_render_lineage(key, value)}")
    if event_type == "paper_ledger_event":
        for key in ("realized_delta", "commission_delta"):
            # A value may have arrived through the metadata allowlist above, so
            # test the rendered facts rather than only the top-level dict.
            if not any(fact.startswith(f"{key}=") for fact in facts):
                facts.append(f"{key}=unknown")
    # Ledger imports carry per-order lineage under each order record. Keep the
    # association explicit rather than attributing session-level results to an entry.
    orders = data.get("orders")
    if isinstance(orders, list):
        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = _render_lineage("order_id", order.get("order_id"))
            order_metadata = order.get("metadata")
            lineage = order_metadata.get("research_lineage") if isinstance(order_metadata, dict) else None
            if not isinstance(lineage, dict):
                continue
            rendered = [
                f"{key}={_render_lineage(key, value)}"
                for key, value in lineage.items()
                if key in _HASH_FIELDS or key in _IDENTIFIER_FIELDS
            ]
            if rendered:
                facts.append(f"order_lineage[{order_id}]: " + ", ".join(rendered))
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
