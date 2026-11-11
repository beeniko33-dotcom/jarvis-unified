"""Read-only Deriv public WebSocket tick collector for EUR/USD.

Trust model: the public endpoint is pinned by hostname and uses TLS certificate and
hostname verification in the collector. Deriv's public tick messages are not documented
as individually signed. A caller-supplied TLS marker and a raw-message hash do not attest
which socket delivered the message. The collector therefore stores ticks as unverified
candidates only; it does not grant provider-verification evidence credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from research.forward_validation import ForwardEvidenceStore

DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
PROVIDER = "Deriv"
INSTRUMENT = "EURUSD"
SOURCE = "deriv-public-wss-tick-v1"
INTERVAL = "tick"
STRATEGY_ID = "sma-crossover-long"
STRATEGY_VERSION = "1.0.0"


def resolve_eurusd_symbol(active_symbols: Any) -> str:
    if not isinstance(active_symbols, list):
        raise ValueError("Deriv active_symbols response must be a list")
    matches = []
    for entry in active_symbols:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        display = str(entry.get("display_name", "")).replace("/", "").replace(" ", "").upper()
        if isinstance(symbol, str) and symbol.strip() and (
            display == "EURUSD" or symbol.strip().upper() == "FRXEURUSD"
        ):
            matches.append(symbol.strip())
    matches = sorted(set(matches))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Deriv EUR/USD symbol, found {len(matches)}")
    return matches[0]


def build_tick_observation(
    raw_message: str,
    *,
    deriv_symbol: str,
    received_at: datetime,
    tls_verified: bool,
) -> dict:
    try:
        payload = json.loads(raw_message)
        tick = payload["tick"]
        epoch = int(tick["epoch"])
        quote = Decimal(str(tick["quote"]))
        symbol = tick["symbol"]
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        raise ValueError("malformed Deriv tick payload") from exc
    if payload.get("msg_type") != "tick" or symbol != deriv_symbol:
        raise ValueError("Deriv tick message type or symbol mismatch")
    if not quote.is_finite() or quote <= 0:
        raise ValueError("Deriv tick quote must be positive and finite")
    if not isinstance(received_at, datetime) or received_at.tzinfo is None:
        raise ValueError("collector receive time must be timezone-aware")
    observed = datetime.fromtimestamp(epoch, timezone.utc)
    raw_digest = hashlib.sha256(raw_message.encode("utf-8")).hexdigest()
    return {
        "observed_at": observed.isoformat(),
        "instrument": INSTRUMENT,
        "provider": PROVIDER,
        "source": SOURCE,
        "interval": INTERVAL,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "price": str(quote),
        "deriv_symbol": deriv_symbol,
        "provider_event_id": f"{symbol}:{epoch}:{quote}",
        "collector_received_at": received_at.astimezone(timezone.utc).isoformat(),
        "transport_endpoint": DERIV_PUBLIC_WS,
        "transport_security_claim": "tls_verified" if tls_verified else "unverified",
        "raw_message": raw_message,
        "raw_message_sha256": raw_digest,
    }


def validate_deriv_observation_binding(item: dict) -> bool:
    """Validate payload consistency only; this does not authenticate the provider or socket."""
    try:
        if (
            item.get("provider") != PROVIDER
            or item.get("instrument") != INSTRUMENT
            or item.get("source") != SOURCE
            or item.get("interval") != INTERVAL
            or item.get("transport_endpoint") != DERIV_PUBLIC_WS
        ):
            return False
        raw = item["raw_message"]
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != item["raw_message_sha256"]:
            return False
        payload = json.loads(raw)
        tick = payload["tick"]
        epoch = int(tick["epoch"])
        quote = Decimal(str(tick["quote"]))
        observed = datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="microseconds")
        normalized_observed = datetime.fromisoformat(item["observed_at"]).astimezone(timezone.utc).isoformat(timespec="microseconds")
        return (
            payload.get("msg_type") == "tick"
            and tick.get("symbol") == item.get("deriv_symbol")
            and item.get("deriv_symbol", "").upper() == "FRXEURUSD"
            and str(quote) == str(Decimal(item["price"]))
            and observed == normalized_observed
            and item.get("provider_event_id") == f'{tick["symbol"]}:{epoch}:{quote}'
        )
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        return False


def collect(duration_seconds: int, database: Path, timeout: int = 20) -> dict:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("Install the optional dependency: pip install -e '.[market-data]'") from exc

    # websocket-client validates the certificate chain and hostname. No token,
    # account authorization, proposal, buy, sell, or account endpoint is used.
    ws = websocket.create_connection(
        DERIV_PUBLIC_WS,
        timeout=timeout,
        sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True},
        enable_multithread=False,
    )
    store = ForwardEvidenceStore(
        database,
        instrument=INSTRUMENT,
        provider=PROVIDER,
        interval=INTERVAL,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
    )
    inserted = duplicates = 0
    try:
        ws.send(json.dumps({"active_symbols": "brief", "req_id": 1}))
        symbols_response = json.loads(ws.recv())
        if symbols_response.get("msg_type") != "active_symbols":
            raise RuntimeError("Deriv did not return active_symbols")
        symbol = resolve_eurusd_symbol(symbols_response.get("active_symbols"))
        ws.send(json.dumps({"ticks": symbol, "subscribe": 1, "req_id": 2}))
        deadline = time.monotonic() + duration_seconds
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            received = datetime.now(timezone.utc)
            item = build_tick_observation(
                raw, deriv_symbol=symbol, received_at=received, tls_verified=True
            )
            added = store.ingest(item)
            inserted += int(added)
            duplicates += int(not added)
        report = store.report(30)
        report.update({
            "collector": "Deriv public WSS read-only",
            "deriv_symbol": symbol,
            "new_observations_ingested": inserted,
            "duplicates_ignored": duplicates,
            "trading_actions": 0,
            "account_authentication_used": False,
            "level_3_certification": False,
        })
        return report
    finally:
        try:
            ws.close()
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--db", type=Path, default=Path("var/deriv_eurusd_forward.sqlite3"))
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.timeout < 1:
        parser.error("duration and timeout must be positive")
    result = collect(args.duration_seconds, args.db, args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["event_chain_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
