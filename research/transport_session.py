"""Collector-side transport session boundary records (informational only).

Records what a TLS session *attempted* to establish. They do not authenticate
individual ticks and must never be used to set provenance_verified=True.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TransportSessionRecord:
    """Immutable description of a collector transport session.

    All fields are descriptive. ``evidence_credit`` is always False.
    """

    endpoint: str
    provider: str
    started_at: str
    tls_certificate_verification_requested: bool
    hostname_check_requested: bool
    peer_certificate_sha256: str | None
    collector_identity: str | None
    notes: str
    evidence_credit: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Hard invariant: session records never grant evidence credit.
        payload["evidence_credit"] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def build_deriv_public_session(
    *,
    endpoint: str,
    started_at: datetime | None = None,
    peer_certificate_sha256: str | None = None,
    collector_identity: str | None = None,
    tls_certificate_verification_requested: bool = True,
    hostname_check_requested: bool = True,
) -> TransportSessionRecord:
    """Build a session record for the Deriv public WSS collector.

    Peer certificate digest is optional and best-effort. Absence does not
    upgrade or degrade the hard rule that ticks remain unverified candidates.
    """
    if not endpoint.strip():
        raise ValueError("endpoint is required")
    started = started_at or _utc_now()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    return TransportSessionRecord(
        endpoint=endpoint.strip(),
        provider="Deriv",
        started_at=started.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        tls_certificate_verification_requested=bool(
            tls_certificate_verification_requested
        ),
        hostname_check_requested=bool(hostname_check_requested),
        peer_certificate_sha256=peer_certificate_sha256,
        collector_identity=collector_identity,
        notes=(
            "TLS session metadata only. Deriv public ticks are not individually "
            "signed; this record does not authorize provenance_verified=1."
        ),
        evidence_credit=False,
    )


def assert_no_evidence_credit(record: TransportSessionRecord) -> None:
    if record.evidence_credit or record.to_dict().get("evidence_credit") is not False:
        raise AssertionError("transport session must never grant evidence credit")
