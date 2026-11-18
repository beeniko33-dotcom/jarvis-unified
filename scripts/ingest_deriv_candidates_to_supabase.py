"""Upload unverified Deriv candidate ticks to Jarvis' private Supabase ingest endpoint.

Requires a Supabase secret API key. It is sent only in the apikey header, never as a bearer JWT. Never prints credentials or raw ticks.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def build_request_body(payload: dict) -> dict:
    required = ("observed_at", "price", "provider_event_id", "raw_message_sha256",
                "collector_received_at", "transport_session_id")
    if not isinstance(payload, dict) or any(not payload.get(k) for k in required):
        raise ValueError("candidate payload is incomplete")
    if payload.get("provider") != "Deriv" or payload.get("instrument") != "EURUSD":
        raise ValueError("candidate provider/instrument mismatch")
    if payload.get("provenance_verified") is not False or payload.get("evidence_credit") is not False:
        raise ValueError("candidate trust flags must remain false")
    if payload.get("evidence_class") != "unverified_candidate":
        raise ValueError("candidate evidence class mismatch")
    source_id = "deriv-public-wss-tick-v1:" + str(payload["provider_event_id"])
    values = {
        "price": str(payload["price"]),
        "provider_event_id": str(payload["provider_event_id"]),
        "raw_message_sha256": str(payload["raw_message_sha256"]),
        "collector_received_at": str(payload["collector_received_at"]),
        "transport_session_id": str(payload["transport_session_id"]),
        "transport_endpoint": str(payload.get("transport_endpoint", "")),
        "source": str(payload.get("source", "")),
        "strategy_id": str(payload.get("strategy_id", "")),
        "strategy_version": str(payload.get("strategy_version", "")),
        "evidence_class": "unverified_candidate",
        "provenance_verified": False,
        "evidence_credit": False,
    }
    return {
        "kind": "market_observation",
        "source_id": source_id,
        "symbol": "EURUSD",
        "timeframe": "tick",
        "event_time": str(payload["observed_at"]),
        "values_json": values,
    }


def load_payloads(database: Path) -> list[dict]:
    if not database.is_file():
        raise FileNotFoundError("candidate database does not exist")
    with sqlite3.connect(database) as db:
        rows = db.execute("SELECT payload FROM observations ORDER BY id").fetchall()
    return [json.loads(row[0]) for row in rows]


def post_candidate(base_url: str, secret_api_key: str, body: dict, timeout: int = 15) -> dict:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Supabase URL must be a valid HTTPS origin")
    endpoint = base_url.rstrip("/") + "/functions/v1/jarvis-runtime-ingest"
    encoded = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
    request = urllib.request.Request(
        endpoint, data=encoded, method="POST",
        headers={
            "content-type": "application/json",
            "apikey": secret_api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError("Supabase ingest returned HTTP " + str(response.status))
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not include response bodies or request headers: they may contain sensitive data.
        raise RuntimeError("Supabase ingest returned HTTP " + str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("Supabase ingest endpoint could not be reached") from None
    if result.get("ok") is not True or result.get("provenance") != "candidate_unverified":
        raise RuntimeError("Supabase ingest did not confirm unverified candidate storage")
    return result


def ingest_database(database: Path, base_url: str, secret_api_key: str) -> dict:
    if not secret_api_key.strip():
        raise ValueError("Supabase secret API key is required")
    payloads = load_payloads(database)
    inserted = duplicates = 0
    for payload in payloads:
        result = post_candidate(base_url, secret_api_key, build_request_body(payload))
        inserted += int(result.get("inserted") is True)
        duplicates += int(result.get("duplicate") is True)
    return {
        "status": "PASS",
        "observations_submitted": len(payloads),
        "inserted": inserted,
        "duplicates": duplicates,
        "provenance": "candidate_unverified",
        "forward_validation_credit_awarded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    base_url = os.environ.get("JARVIS_SUPABASE_URL", "")
    key = os.environ.get("JARVIS_SUPABASE_SECRET_KEY") or os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not key:
        parser.error("JARVIS_SUPABASE_URL and JARVIS_SUPABASE_SECRET_KEY are required")
    print(json.dumps(ingest_database(args.db, base_url, key), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
