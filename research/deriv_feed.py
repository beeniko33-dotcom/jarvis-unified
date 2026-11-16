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
from research.transport_session import DERIV_PUBLIC_WS, build_deriv_public_session

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
    conflicts = []
    for entry in active_symbols:
        if not isinstance(entry, dict):
            continue
        symbol_codes = []
        for key in ("symbol", "underlying_symbol"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                symbol_codes.append(value.strip())
        if len({code.upper() for code in symbol_codes}) > 1:
            raise ValueError("Deriv active_symbols entry has conflicting symbol codes")
        if not symbol_codes:
            continue
        code = symbol_codes[0]
        display_name = entry.get("display_name") or entry.get("underlying_symbol_name", "")
        display = str(display_name).replace("/", "").replace(" ", "").upper()
        if code.upper() == "FRXEURUSD":
            matches.append(code)
        elif display == "EURUSD":
            # Claims to be EUR/USD but does not carry the canonical Deriv code.
            # validate_deriv_observation_binding() requires the literal FRXEURUSD, so
            # returning this would resolve a symbol that can never pass the binding
            # check and would abort collection on the first tick. Fail closed instead
            # of silently ignoring it: a mislabelled symbol is a data-integrity fault.
            conflicts.append(code)
    if conflicts:
        raise ValueError(
            "symbol(s) claim EUR/USD without the canonical FRXEURUSD code: "
            + ", ".join(sorted(set(conflicts)))
        )
    matches = sorted(set(matches))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Deriv EUR/USD symbol, found {len(matches)}")
    return matches[0]


def build_tick_observation(
    raw_message: str,
    *,
    deriv_symbol: str,
    received_at: datetime,
    transport_session: dict,
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
    if not isinstance(transport_session, dict):
        raise ValueError("an established transport session record is required")
    session_id = transport_session.get("session_id")
    if (
        not session_id
        or transport_session.get("endpoint") != DERIV_PUBLIC_WS
        or transport_session.get("provider") != PROVIDER
        or transport_session.get("tls_socket_observed") is not True
        or transport_session.get("evidence_credit") is not False
    ):
        raise ValueError("transport session record is missing required socket binding")
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
        "transport_session_id": session_id,
        "transport_session": transport_session,
        "transport_security_claim": "unverified",
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
        session = item["transport_session"]
        if (
            not isinstance(session, dict)
            or session.get("session_id") != item.get("transport_session_id")
            or session.get("endpoint") != DERIV_PUBLIC_WS
            or session.get("provider") != PROVIDER
            or session.get("tls_socket_observed") is not True
            or session.get("evidence_credit") is not False
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
    session_started_at = datetime.now(timezone.utc)
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
        tls_socket = getattr(ws, "sock", None)
        session_record = build_deriv_public_session(
            endpoint=DERIV_PUBLIC_WS,
            tls_socket=tls_socket,
            started_at=session_started_at,
        ).to_dict()
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
                raw, deriv_symbol=symbol, received_at=received,
                transport_session=session_record,
            )
            if not validate_deriv_observation_binding(item):
                raise RuntimeError("collector observation failed payload/session binding checks")
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


def exit_code_for_report(report: dict) -> int:
    """Map an evidence report to a process exit code.

    Success requires the gate to actually PASS. An intact hash chain over zero
    observations is trivially valid and must not be read as success: a cron job or
    CI step would otherwise report green while no evidence exists at all.
    """
    return 0 if report.get("level_3_forward_evidence_gate") == "PASS" else 1


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
    return exit_code_for_report(result)


if __name__ == "__main__":
    raise SystemExit(main())


def reconcile_live_history(live_ticks: list[tuple[int, str]], response: dict) -> dict:
    """Cross-check overlapping live ticks against Deriv history, never prove provenance."""
    if not isinstance(live_ticks, list) or not live_ticks:
        raise ValueError("at least one live tick is required for reconciliation")
    if not isinstance(response, dict) or response.get("msg_type") != "history":
        raise ValueError("Deriv history response has an unexpected message type")
    history = response.get("history")
    if not isinstance(history, dict):
        raise ValueError("Deriv history payload is missing")
    times, prices = history.get("times"), history.get("prices")
    if not isinstance(times, list) or not isinstance(prices, list) or len(times) != len(prices):
        raise ValueError("Deriv history times/prices must be equally sized lists")

    def normalize(pairs, label):
        normalized = {}
        for epoch, raw_quote in pairs:
            if isinstance(epoch, bool) or not isinstance(epoch, int):
                raise ValueError(f"{label} epoch must be an integer")
            quote = Decimal(str(raw_quote))
            if not quote.is_finite() or quote <= 0:
                raise ValueError(f"{label} quote must be positive and finite")
            previous = normalized.get(epoch)
            if previous is not None and previous != quote:
                raise ValueError(f"conflicting {label} quotes share a provider epoch")
            normalized[epoch] = quote
        return normalized

    if any(not isinstance(pair, (tuple, list)) or len(pair) != 2 for pair in live_ticks):
        raise ValueError("malformed live tick pair")
    live = normalize(live_ticks, "live")
    historical = normalize(list(zip(times, prices)), "historical")
    overlap = sorted(set(live) & set(historical))
    if not overlap:
        raise ValueError("live and historical tick samples have no overlapping epochs")
    mismatches = [
        {"epoch": epoch, "live_quote": str(live[epoch]), "history_quote": str(historical[epoch])}
        for epoch in overlap if live[epoch] != historical[epoch]
    ]
    if mismatches:
        raise ValueError(f"live/history quote mismatches: {mismatches!r}")
    return {
        "overlap_count": len(overlap),
        "exact_matches": len(overlap),
        "mismatch_count": 0,
        "unmatched_live_ticks": len(set(live) - set(historical)),
        "first_overlap_epoch": overlap[0],
        "last_overlap_epoch": overlap[-1],
        "consistency_check": "PASS",
        "evidence_credit": False,
        "provenance_verified": False,
    }
