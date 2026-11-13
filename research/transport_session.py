"""Informational TLS session records; never grant forward-evidence credit."""
from __future__ import annotations

import hashlib
import json
import ssl
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TransportSessionRecord:
    """Immutable facts observed from the collector's established TLS socket.

    These facts describe transport only. They do not authenticate individual
    ticks, prove quote truth, or grant forward-evidence credit.
    """

    session_id: str
    endpoint: str
    provider: str
    started_at: str
    tls_socket_observed: bool
    peer_certificate_present: bool
    peer_certificate_sha256: str | None
    certificate_verification_mode: str
    hostname_check_enabled: bool
    collector_identity: str | None
    notes: str
    evidence_credit: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_credit"] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _validate_deriv_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("endpoint is required")
    normalized = endpoint.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "wss"
        or parsed.hostname != "api.derivws.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/trading/v1/options/ws/public"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("endpoint must be the exact approved Deriv public WSS endpoint")
    return normalized


def build_deriv_public_session(
    *,
    endpoint: str,
    tls_socket: ssl.SSLSocket,
    started_at: datetime | None = None,
    collector_identity: str | None = None,
) -> TransportSessionRecord:
    """Record actual properties of the established TLS socket.

    A real SSLSocket with CERT_REQUIRED, hostname checking enabled, and a
    presented peer certificate is required. This is descriptive metadata only;
    even a successful record has evidence_credit=False.
    """
    normalized_endpoint = _validate_deriv_endpoint(endpoint)
    if not isinstance(tls_socket, ssl.SSLSocket):
        raise ValueError("an established TLS SSLSocket is required")
    context = tls_socket.context
    if context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("TLS socket is not configured with CERT_REQUIRED")
    if not context.check_hostname:
        raise ValueError("TLS socket hostname verification is not enabled")
    certificate_der = tls_socket.getpeercert(binary_form=True)
    if not certificate_der:
        raise ValueError("TLS peer certificate is unavailable")
    started = started_at or _utc_now()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    started_iso = started.astimezone(timezone.utc).isoformat(timespec="microseconds")
    certificate_digest = hashlib.sha256(certificate_der).hexdigest()
    identity = (collector_identity or "").strip() or None
    session_material = json.dumps(
        [normalized_endpoint, started_iso, certificate_digest, identity],
        separators=(",", ":"),
    ).encode("utf-8")
    session_id = hashlib.sha256(session_material).hexdigest()
    return TransportSessionRecord(
        session_id=session_id,
        endpoint=normalized_endpoint,
        provider="Deriv",
        started_at=started_iso,
        tls_socket_observed=True,
        peer_certificate_present=True,
        peer_certificate_sha256=certificate_digest,
        certificate_verification_mode="CERT_REQUIRED",
        hostname_check_enabled=True,
        collector_identity=identity,
        notes=(
            "Observed TLS socket metadata only. This does not authenticate individual "
            "ticks, establish non-repudiation, or authorize provenance_verified=1."
        ),
        evidence_credit=False,
    )


def assert_no_evidence_credit(record: TransportSessionRecord) -> None:
    if record.evidence_credit or record.to_dict().get("evidence_credit") is not False:
        raise AssertionError("transport session must never grant evidence credit")
