"""Allowlisted public RSS/Atom headline metadata intake.

This module parses caller-supplied feed bytes only. It performs no network
requests, article-page fetches, login, paywall access, or body extraction.
All records remain candidate_unverified.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

MAX_FEED_BYTES = 1_000_000
MAX_ITEMS = 500
MAX_TITLE_LENGTH = 500
_TAGS = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class HeadlineRecord:
    publisher: str
    feed_url: str
    article_url: str
    title: str
    published_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    provenance: str = "candidate_unverified"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only credential-free HTTPS URLs are permitted")
    return parsed.hostname.lower()


def _clean_title(value: str) -> str:
    value = html.unescape(_TAGS.sub(" ", value or ""))
    return " ".join(value.split())[:MAX_TITLE_LENGTH]


def _parse_time(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def parse_public_feed(
    payload: bytes,
    *,
    publisher: str,
    feed_url: str,
    allowed_feed_hosts: Iterable[str],
    allowed_article_hosts: Iterable[str],
    retrieved_at: datetime,
) -> list[HeadlineRecord]:
    """Parse RSS 2.0 or Atom 1.0 headline metadata with explicit host allowlists."""
    if not isinstance(payload, bytes) or len(payload) > MAX_FEED_BYTES:
        raise ValueError("feed payload must be bytes within the 1 MB limit")
    if not publisher.strip():
        raise ValueError("publisher is required")
    feed_host = _host(feed_url)
    feed_allow = {h.lower().strip() for h in allowed_feed_hosts if h.strip()}
    article_allow = {h.lower().strip() for h in allowed_article_hosts if h.strip()}
    if not feed_allow or feed_host not in feed_allow:
        raise ValueError("feed host is not explicitly allowlisted")
    if not article_allow:
        raise ValueError("at least one article host must be allowlisted")
    retrieved = _utc(retrieved_at, "retrieved_at")
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("DTD and entity declarations are not permitted")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("feed XML is malformed") from exc

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    is_atom = root.tag.rsplit("}", 1)[-1].lower() == "feed"
    elements = root.findall("atom:entry", namespace) if is_atom else root.findall(".//item")
    if len(elements) > MAX_ITEMS:
        raise ValueError("feed contains more than 500 entries")

    records: list[HeadlineRecord] = []
    for item in elements:
        if is_atom:
            title_node = item.find("atom:title", namespace)
            link_node = next(
                (node for node in item.findall("atom:link", namespace)
                 if node.attrib.get("rel", "alternate") == "alternate" and node.attrib.get("href")),
                None,
            )
            link = link_node.attrib["href"] if link_node is not None else ""
            date_node = item.find("atom:published", namespace) or item.find("atom:updated", namespace)
            published_text = date_node.text if date_node is not None else None
        else:
            title_node = item.find("title")
            link_node = item.find("link")
            link = (link_node.text or "").strip() if link_node is not None else ""
            date_node = item.find("pubDate")
            published_text = date_node.text if date_node is not None else None

        title = _clean_title(title_node.text if title_node is not None else "")
        if not title or not link:
            continue
        try:
            article_host = _host(link)
        except ValueError:
            continue
        if article_host not in article_allow:
            continue
        published = _parse_time(published_text)
        canonical = json.dumps(
            {
                "publisher": publisher.strip(),
                "feed_url": feed_url,
                "article_url": link,
                "title": title,
                "published_at": published.isoformat() if published else None,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        records.append(HeadlineRecord(
            publisher=publisher.strip(), feed_url=feed_url, article_url=link,
            title=title, published_at=published, retrieved_at=retrieved,
            content_hash=digest,
        ))
    return records


def store_headlines(records: Iterable[HeadlineRecord], database: str | Path) -> dict[str, int]:
    """Append headline metadata with hash-based deduplication; never stores article bodies."""
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    inserted = duplicates = processed = 0
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS public_headlines (
                content_hash TEXT PRIMARY KEY,
                publisher TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                article_url TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                retrieved_at TEXT NOT NULL,
                provenance TEXT NOT NULL CHECK(provenance = 'candidate_unverified')
            )
        """)
        db.executescript("""
            CREATE TRIGGER IF NOT EXISTS public_headlines_no_update
            BEFORE UPDATE ON public_headlines BEGIN
                SELECT RAISE(ABORT, 'public_headlines is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS public_headlines_no_delete
            BEFORE DELETE ON public_headlines BEGIN
                SELECT RAISE(ABORT, 'public_headlines is append-only');
            END;
        """)
        for record in records:
            processed += 1
            cursor = db.execute("""
                INSERT OR IGNORE INTO public_headlines
                (content_hash, publisher, feed_url, article_url, title,
                 published_at, retrieved_at, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate_unverified')
            """, (
                record.content_hash, record.publisher, record.feed_url,
                record.article_url, record.title,
                _utc(record.published_at, "published_at").isoformat() if record.published_at else None,
                _utc(record.retrieved_at, "retrieved_at").isoformat(),
            ))
            if cursor.rowcount:
                inserted += 1
            else:
                duplicates += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "processed": processed, "inserted": inserted, "duplicates": duplicates,
        "verified_headlines": 0,
    }
