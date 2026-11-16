"""Explicitly allowlisted, research-only public data adapters.

Network access occurs only when a caller explicitly invokes fetch_frankfurter_daily.
Historical CSV import reads a caller-provided local file and never downloads it.
No broker/account/order functionality is present.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from research.evidence_pipeline import MarketObservation, ResearchEvidencePipeline

FRANKFURTER_HOST = "api.frankfurter.dev"
FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
MAX_RESPONSE_BYTES = 256_000
USER_AGENT = "JarvisUnifiedResearch/0.1 (research-only; contact repository maintainer)"


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    publisher: str
    source_url: str
    terms_url: str
    retrieved_at: datetime
    licence_status: str
    data_class: str


@dataclass(frozen=True)
class PublicSourceRecord:
    observation: MarketObservation
    metadata: SourceMetadata


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal(value: str, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{field} must be a decimal number") from None
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{field} must be finite and greater than zero")
    return result


def fetch_frankfurter_daily(
    rate_date: date,
    *,
    base: str = "EUR",
    quote: str = "USD",
    timeout_seconds: float = 10,
    now: datetime | None = None,
) -> PublicSourceRecord:
    """Fetch one daily reference rate; it is not a live/intraday trading quote."""
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be between 0 and 30")
    base, quote = base.upper(), quote.upper()
    if len(base) != 3 or len(quote) != 3 or not base.isalpha() or not quote.isalpha():
        raise ValueError("base and quote must be three-letter currency codes")
    if base == quote:
        raise ValueError("base and quote currencies must differ")
    query = urllib.parse.urlencode({"from": base, "to": quote})
    url = f"{FRANKFURTER_BASE}/{rate_date.isoformat()}?{query}"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != FRANKFURTER_HOST:
        raise ValueError("source URL is not on the explicit HTTPS allowlist")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError(f"Frankfurter returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Frankfurter returned HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Frankfurter request failed: {exc.reason}") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Frankfurter response exceeded size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
        returned_date = date.fromisoformat(payload["date"])
        rate = _decimal(str(payload["rates"][quote]), "rate")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Frankfurter response did not match the expected schema") from exc
    if returned_date != rate_date:
        raise RuntimeError("provider returned a different reference date")
    received = _aware_utc(now or datetime.now(timezone.utc), "now")
    event_time = datetime.combine(returned_date, time.min, tzinfo=timezone.utc)
    observation = MarketObservation(
        source_id="frankfurter_daily_reference",
        event_time=event_time,
        received_at=received,
        symbol=f"{base}{quote}",
        timeframe="1d-reference",
        values={"rate": float(rate), "base": base, "quote": quote, "data_class": "daily_reference_rate"},
    )
    metadata = SourceMetadata(
        source_id="frankfurter_daily_reference",
        publisher="Frankfurter",
        source_url=url,
        terms_url="https://frankfurter.dev/",
        retrieved_at=received,
        licence_status="review_provider_terms_before_redistribution",
        data_class="daily_reference_rate_not_execution_quote",
    )
    return PublicSourceRecord(observation, metadata)


def read_historical_ohlcv_csv(
    path: str | Path,
    *,
    symbol: str,
    timeframe: str,
    source_id: str = "user_supplied_historical_csv",
    now: datetime | None = None,
) -> list[PublicSourceRecord]:
    """Read a local OHLCV CSV. Required columns: timestamp,open,high,low,close.

    Optional volume is retained when present. Timestamp must be ISO-8601 and
    timezone-aware. This parser does not assert the file's origin or licence.
    """
    if not symbol.strip() or not timeframe.strip() or not source_id.strip():
        raise ValueError("symbol, timeframe and source_id are required")
    received = _aware_utc(now or datetime.now(timezone.utc), "now")
    records: list[PublicSourceRecord] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV requires timestamp,open,high,low,close columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                event_time = _aware_utc(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")), "timestamp")
                opening = _decimal(row["open"], "open")
                high = _decimal(row["high"], "high")
                low = _decimal(row["low"], "low")
                close = _decimal(row["close"], "close")
                if high < max(opening, close, low) or low > min(opening, close, high):
                    raise ValueError("OHLC relationship is invalid")
                values = {
                    "open": float(opening), "high": float(high),
                    "low": float(low), "close": float(close),
                    "data_class": "historical_ohlcv_user_supplied",
                }
                if row.get("volume", "").strip():
                    volume = Decimal(row["volume"])
                    if not volume.is_finite() or volume < 0:
                        raise ValueError("volume must be finite and non-negative")
                    values["volume"] = float(volume)
            except (ValueError, InvalidOperation, AttributeError) as exc:
                raise ValueError(f"invalid CSV row {line_number}: {exc}") from None
            observation = MarketObservation(
                source_id=source_id, event_time=event_time, received_at=received,
                symbol=symbol.upper(), timeframe=timeframe, values=values,
            )
            metadata = SourceMetadata(
                source_id=source_id, publisher="User-supplied file",
                source_url=f"local-file:{Path(path).name}",
                terms_url="not-provided",
                retrieved_at=received,
                licence_status="unknown_user_must_confirm_rights",
                data_class="historical_ohlcv_candidate_unverified",
            )
            records.append(PublicSourceRecord(observation, metadata))
    return records


def ingest_public_records(
    records: Iterable[PublicSourceRecord],
    *,
    pipeline: ResearchEvidencePipeline,
    provenance_database: str | Path,
    now: datetime | None = None,
) -> dict[str, int]:
    """Ingest observations and persist their provenance in a sidecar SQLite DB.

    The existing evidence pipeline remains authoritative for observation intake.
    This sidecar preserves source URL, publisher, terms and retrieval metadata.
    It does not promote any record to verified evidence.
    """
    received = _aware_utc(now or datetime.now(timezone.utc), "now")
    provenance_path = Path(provenance_database)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(provenance_path), timeout=10)
    accepted = duplicates = processed = 0
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS public_source_provenance (
                content_hash TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_url TEXT NOT NULL,
                terms_url TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                licence_status TEXT NOT NULL,
                data_class TEXT NOT NULL,
                provenance TEXT NOT NULL CHECK(provenance = 'candidate_unverified')
            )
        """)
        pending = list(records)
        for record in pending:
            processed += 1
            meta = record.metadata
            db.execute("""
                INSERT OR IGNORE INTO public_source_provenance
                (content_hash, source_id, publisher, source_url, terms_url,
                 retrieved_at, licence_status, data_class, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate_unverified')
            """, (
                record.observation.content_hash, meta.source_id, meta.publisher,
                meta.source_url, meta.terms_url, _aware_utc(meta.retrieved_at, "retrieved_at").isoformat(),
                meta.licence_status, meta.data_class,
            ))
        # Commit provenance first: an intake failure can leave an orphan metadata
        # row, but cannot leave an ingested observation without its source record.
        db.commit()
        for record in pending:
            result = pipeline.ingest(record.observation, now=received)
            if result.accepted:
                accepted += 1
            if result.duplicate:
                duplicates += 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "provenance_records": processed,
        "verified_observations": 0,
        "evidence_eligible": 0,
    }
