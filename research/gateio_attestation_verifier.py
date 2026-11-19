"""Independent Gate.io public-data attestation signer.

Run this in a separately controlled verifier environment, never inside the
paper runner. The private Ed25519 key is read only from the verifier process
environment. This module only signs snapshots it fetched itself over Gate.io's
public HTTPS API; it has no order, wallet, or private-account endpoints.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE_URL = "https://api.gateio.ws/api/v4"
SOURCE = "gateio-spot-public-rest-v1"
VERIFIER_ID = "jarvis-independent-gateio-verifier-v1"
DURATION_SECONDS = 300


def canonical_observation(observation: dict) -> bytes:
    """Match the paper planner's canonical signing format exactly."""
    signed_fields = {
        key: value for key, value in observation.items()
        if key not in {"trust_attestation", "provenance_verified", "evidence_credit"}
    }
    return json.dumps(
        signed_fields, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _get_json(path: str, *, opener: Callable = urlopen, timeout: float = 10):
    request = Request(
        BASE_URL + path,
        headers={"Accept": "application/json", "User-Agent": "JarvisIndependentVerifier/1.0"},
    )
    response = opener(request, timeout=timeout)
    try:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"Gate.io public API returned HTTP {response.status}")
        # Refuse redirects away from the exact Gate.io API host.
        if response.geturl().split("/")[2].lower() != "api.gateio.ws":
            raise RuntimeError("Gate.io API redirected to an unexpected host")
        raw = response.read()
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    return json.loads(raw), raw


def _positive_decimal(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def fetch_and_attest(
    symbol: str = "BTC_USDT",
    *,
    private_key_b64: str | None = None,
    opener: Callable = urlopen,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Fetch server time, 50 completed 5m closes and top-of-book, then sign."""
    if not isinstance(symbol, str) or not symbol.endswith("_USDT") or not symbol.replace("_", "").isalnum():
        raise ValueError("symbol must be a Gate.io USDT spot pair such as BTC_USDT")
    key_text = private_key_b64 or os.environ.get("JARVIS_GATEIO_ATTESTATION_PRIVATE_KEY_B64")
    if not isinstance(key_text, str) or not key_text:
        raise RuntimeError("verifier signing key is not configured")
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_text, validate=True))
    except Exception as exc:
        raise RuntimeError("verifier signing key is invalid") from exc

    local_received = now()
    if local_received.tzinfo is None or local_received.utcoffset() is None:
        raise ValueError("verifier clock must be timezone-aware")
    local_received = local_received.astimezone(timezone.utc)

    server, server_raw = _get_json("/spot/time", opener=opener)
    if not isinstance(server, dict) or isinstance(server.get("server_time"), bool):
        raise ValueError("Gate.io server-time response is malformed")
    server_time_ms = int(server["server_time"])
    if server_time_ms < 1_000_000_000_000:
        raise ValueError("Gate.io server time must be Unix milliseconds")
    server_time = datetime.fromtimestamp(server_time_ms / 1000, timezone.utc)
    server_seconds = server_time_ms // 1000
    clock_skew_ms = int((local_received - server_time).total_seconds() * 1000)

    query = urlencode({"currency_pair": symbol, "interval": "5m", "limit": 100})
    candles, candles_raw = _get_json("/spot/candlesticks?" + query, opener=opener)
    if not isinstance(candles, list):
        raise ValueError("Gate.io candle response is malformed")
    parsed = []
    for row in candles:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError("Gate.io candle row is malformed")
        start = int(row[0])
        close = _positive_decimal(row[2], "candle close")
        end = start + DURATION_SECONDS
        if end <= server_seconds:
            parsed.append((start, end, close))
    parsed.sort(key=lambda item: item[0])
    # Deduplicate by candle start, rejecting conflicting provider rows.
    dedup = {}
    for start, end, close in parsed:
        if start in dedup and dedup[start] != (end, close):
            raise ValueError("Gate.io returned conflicting duplicate candles")
        dedup[start] = (end, close)
    history = sorted((start, end, close) for start, (end, close) in dedup.items())
    if len(history) < 50:
        raise ValueError("fewer than 50 completed 5m candles returned")
    history = history[-50:]
    if any(history[i][0] - history[i - 1][0] != DURATION_SECONDS for i in range(1, len(history))):
        raise ValueError("completed candle history contains a gap or duplicate")
    latest_start, latest_end, _ = history[-1]
    age = server_seconds - latest_end
    if age < 0 or age > 480:
        raise ValueError("latest completed 5m candle is stale")

    book_query = urlencode({"currency_pair": symbol, "limit": 1})
    book, book_raw = _get_json("/spot/order_book?" + book_query, opener=opener)
    if not isinstance(book, dict) or not book.get("bids") or not book.get("asks"):
        raise ValueError("Gate.io order book is missing bid or ask")
    best_bid, best_ask = book["bids"][0], book["asks"][0]
    if (not isinstance(best_bid, list) or len(best_bid) < 2
            or not isinstance(best_ask, list) or len(best_ask) < 2):
        raise ValueError("Gate.io order-book levels must be price/quantity arrays")
    bid = _positive_decimal(best_bid[0], "best bid")
    ask = _positive_decimal(best_ask[0], "best ask")
    if bid > ask:
        raise ValueError("Gate.io order book is crossed")

    observation = {
        "provider": "Gate.io",
        "source": SOURCE,
        "instrument": symbol,
        "interval": "5m",
        "complete": True,
        "event_time": datetime.fromtimestamp(latest_end, timezone.utc).isoformat(),
        "received_at": local_received.isoformat(),
        "clock_skew_ms": clock_skew_ms,
        "bid": str(bid),
        "ask": str(ask),
        "closes": [str(item[2]) for item in history],
        "raw_payload_sha256": hashlib.sha256(
            server_raw + b"\n" + candles_raw + b"\n" + book_raw
        ).hexdigest(),
        "provider_server_time": server_time.isoformat(),
        "provider_candle_start": latest_start,
        "provider_candle_end": latest_end,
        "provider_orderbook_update_id": book.get("id"),
        "verifier_observed_at": local_received.isoformat(),
    }
    signature = private_key.sign(canonical_observation(observation))
    observation["trust_attestation"] = {
        "verifier_id": VERIFIER_ID,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    # The verifier's output does not self-award evidence credit. The downstream
    # reviewer still checks key allowlisting, revocation, age, and policy.
    observation["provenance_verified"] = False
    observation["evidence_credit"] = False
    return observation
