"""Safe normalization for remote-job and affiliate opportunity records.

This is a data model only: it performs no scraping, network requests, or
application submissions. Imported descriptions are untrusted content.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import re
from urllib.parse import urlsplit, urlunsplit


MAX_TITLE = 240
MAX_DESCRIPTION = 8000
_SUSPICIOUS_TEXT = (
    (re.compile(r"\b(upfront fee|pay to apply|registration fee)\b", re.I), "upfront_fee_request"),
    (re.compile(r"\b(guaranteed income|guaranteed salary|instant riches)\b", re.I), "unrealistic_income_claim"),
    (re.compile(r"\b(crypto deposit|send bitcoin|wallet deposit)\b", re.I), "crypto_payment_request"),
    (re.compile(r"\b(whatsapp only|telegram only)\b", re.I), "off_platform_only_contact"),
)


def _clean_text(value: str, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > limit:
        raise ValueError(f"{field} must contain 1-{limit} characters")
    return cleaned


def canonical_source_url(value: str) -> str:
    """Require HTTPS, reject embedded credentials and normalize URL identity."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("source_url must be a valid HTTPS URL")
    parts = urlsplit(value.strip())
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError("source_url must use HTTPS and include a hostname")
    if parts.username or parts.password:
        raise ValueError("source_url cannot contain embedded credentials")
    if parts.port not in (None, 443):
        raise ValueError("non-standard source URL ports are not accepted")
    host = parts.hostname.lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host:
        raise ValueError("source_url hostname is invalid")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    # Fragments and tracking query strings are excluded from identity. The
    # original source URL is retained separately for attribution.
    return urlunsplit(("https", host, path.rstrip("/") or "/", "", ""))


@dataclass(frozen=True, slots=True)
class OpportunityRecord:
    title: str
    description: str
    category: str
    source_url: str
    canonical_url: str
    source_domain: str
    fingerprint: str
    country_eligibility: tuple[str, ...]
    compensation_text: str | None
    published_at: datetime | None
    risk_flags: tuple[str, ...]
    verification_status: str
    external_submission_allowed: bool = False


def normalize_opportunity(
    *,
    title: str,
    description: str,
    category: str,
    source_url: str,
    country_eligibility: tuple[str, ...] = (),
    compensation_text: str | None = None,
    published_at: datetime | None = None,
) -> OpportunityRecord:
    """Normalize a listing and attach review flags; never marks it verified."""
    clean_title = _clean_text(title, "title", MAX_TITLE)
    clean_description = _clean_text(description, "description", MAX_DESCRIPTION)
    clean_category = _clean_text(category, "category", 40).lower()
    if clean_category not in {"remote_job", "freelance", "affiliate", "ai_tool", "digital_product"}:
        raise ValueError("unsupported opportunity category")
    canonical = canonical_source_url(source_url)
    original_parts = urlsplit(source_url.strip())
    domain = (original_parts.hostname or "").lower().rstrip(".")
    if published_at is not None:
        if not isinstance(published_at, datetime) or published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")
        published_at = published_at.astimezone(timezone.utc)
    countries = tuple(sorted({c.strip().upper() for c in country_eligibility if isinstance(c, str) and c.strip()}))
    if any(len(country) > 3 for country in countries):
        raise ValueError("country eligibility entries must be ISO-style short codes")
    if compensation_text is not None:
        compensation_text = _clean_text(compensation_text, "compensation_text", 240)
    flags = tuple(flag for pattern, flag in _SUSPICIOUS_TEXT if pattern.search(clean_title + " " + clean_description))
    fingerprint = sha256(f"{clean_title.casefold()}|{canonical}".encode("utf-8")).hexdigest()
    return OpportunityRecord(
        title=clean_title,
        description=clean_description,
        category=clean_category,
        source_url=source_url.strip(),
        canonical_url=canonical,
        source_domain=domain,
        fingerprint=fingerprint,
        country_eligibility=countries,
        compensation_text=compensation_text,
        published_at=published_at,
        risk_flags=flags,
        verification_status="unverified",
        external_submission_allowed=False,
    )
