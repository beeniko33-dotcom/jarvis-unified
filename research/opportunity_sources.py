"""Explicit source registry for compliant opportunity discovery.

Registry validation only: no crawler, scraping, browser automation, or HTTP
request is performed here. Every enabled source must have documented terms
and robots-policy URLs and an operator-approved host allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from research.opportunity_records import canonical_source_url


class SourceMethod(StrEnum):
    OFFICIAL_API = "official_api"
    RSS = "rss"
    PUBLIC_ATS = "public_ats"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class OpportunitySource:
    source_id: str
    display_name: str
    allowed_domain: str
    method: SourceMethod
    categories: frozenset[str]
    terms_url: str
    robots_url: str
    minimum_interval_seconds: int
    enabled: bool = False


def validate_source(source: OpportunitySource) -> OpportunitySource:
    """Reject unsafe/incomplete sources; disabled is the default."""
    if not isinstance(source, OpportunitySource):
        raise ValueError("source must be an OpportunitySource")
    if not source.source_id or len(source.source_id) > 80:
        raise ValueError("source_id must contain 1-80 characters")
    if not source.display_name or len(source.display_name) > 120:
        raise ValueError("display_name must contain 1-120 characters")
    domain = source.allowed_domain.lower().rstrip(".")
    if not domain or "/" in domain or ":" in domain or "." not in domain:
        raise ValueError("allowed_domain must be a bare hostname")
    for url in (source.terms_url, source.robots_url):
        canonical_source_url(url)
        if (urlsplit(url).hostname or "").lower().rstrip(".") != domain:
            raise ValueError("terms and robots URLs must be hosted on the allowlisted domain")
    if not source.categories or not source.categories <= {
        "remote_job", "freelance", "affiliate", "ai_tool", "digital_product"
    }:
        raise ValueError("source categories are empty or unsupported")
    if not isinstance(source.minimum_interval_seconds, int) or source.minimum_interval_seconds < 60:
        raise ValueError("minimum_interval_seconds must be at least 60")
    if not isinstance(source.enabled, bool):
        raise ValueError("enabled must be boolean")
    return source


def source_accepts_url(source: OpportunitySource, url: str) -> bool:
    """Match an HTTPS URL to the exact host or a real subdomain boundary."""
    validate_source(source)
    host = (urlsplit(canonical_source_url(url)).hostname or "").lower()
    domain = source.allowed_domain.lower().rstrip(".")
    return source.enabled and (host == domain or host.endswith("." + domain))
