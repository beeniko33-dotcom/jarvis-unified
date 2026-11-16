"""Bounded, read-only smoke test for Deriv's documented public market-data feed.

This validates endpoint TLS and the live public symbol/tick protocol only. It does
not authenticate individual ticks, grant evidence credit, or place trades.
"""
from __future__ import annotations

import argparse
import json
import ssl
import time
from datetime import datetime, timezone

from research.deriv_feed import resolve_eurusd_symbol
from research.transport_session import DERIV_PUBLIC_WS, build_deriv_public_session


def run(duration_seconds: int, timeout_seconds: int) -> dict:
    import websocket

    ws = websocket.create_connection(
        DERIV_PUBLIC_WS,
        timeout=timeout_seconds,
        sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True},
        enable_multithread=False,
    )
    try:
        session = build_deriv_public_session(
            endpoint=DERIV_PUBLIC_WS,
            tls_socket=ws.sock,
            started_at=datetime.now(timezone.utc),
            collector_identity="jarvis-deriv-public-smoke",
        ).to_dict()
        ws.send(json.dumps({"active_symbols": "brief", "req_id": 1}))
        symbols_response = json.loads(ws.recv())
        if symbols_response.get("msg_type") != "active_symbols":
            raise RuntimeError(f"unexpected active_symbols response: {symbols_response!r}")
        symbol = resolve_eurusd_symbol(symbols_response.get("active_symbols"))

        ws.send(json.dumps({"ticks": symbol, "subscribe": 1, "req_id": 2}))
        deadline = time.monotonic() + duration_seconds
        received = 0
        last_epoch = None
        duplicates = 0
        last_ping = time.monotonic()
        # Short bounded receive waits let the probe schedule keepalives.
        ws.settimeout(min(5, timeout_seconds))
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now - last_ping >= 30:
                ws.send(json.dumps({"ping": 1, "req_id": 30}))
                last_ping = now
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException as exc:
                return {
                    "status": "connection_lost",
                    "provider": "Deriv",
                    "endpoint": DERIV_PUBLIC_WS,
                    "symbol": symbol,
                    "ticks_received": received,
                    "transport_session": session,
                    "evidence_credit": False,
                    "level_3_certification": False,
                    "trading_actions": 0,
                    "detail": str(exc),
                }
            payload = json.loads(raw)
            if payload.get("error"):
                error = payload["error"]
                code = str(error.get("code", ""))
                if "MarketIsClosed" in code or "MarketIsClosed" in str(error.get("message", "")):
                    return {
                        "status": "market_closed",
                        "provider": "Deriv",
                        "endpoint": DERIV_PUBLIC_WS,
                        "symbol": symbol,
                        "ticks_received": received,
                        "transport_session": session,
                        "evidence_credit": False,
                        "level_3_certification": False,
                        "detail": error,
                    }
                raise RuntimeError(f"Deriv returned an API error: {error!r}")
            if payload.get("msg_type") != "tick":
                continue
            tick = payload.get("tick")
            if not isinstance(tick, dict) or tick.get("symbol") != symbol:
                raise RuntimeError("tick payload missing or symbol mismatch")
            epoch = tick.get("epoch")
            quote = tick.get("quote")
            if not isinstance(epoch, int) or not isinstance(quote, (int, float)):
                raise RuntimeError("tick epoch/quote has an unexpected type")
            if quote <= 0:
                raise RuntimeError("tick quote must be positive")
            if last_epoch is not None:
                if epoch < last_epoch:
                    raise RuntimeError("tick event timestamp moved backwards")
                if epoch == last_epoch:
                    duplicates += 1
            last_epoch = epoch
            received += 1

        return {
            "status": "ticks_observed" if received else "no_ticks_observed",
            "provider": "Deriv",
            "endpoint": DERIV_PUBLIC_WS,
            "symbol": symbol,
            "ticks_received": received,
            "duplicate_second_timestamps": duplicates,
            "last_provider_epoch": last_epoch,
            "transport_session": session,
            "evidence_credit": False,
            "level_3_certification": False,
            "trading_actions": 0,
        }
    finally:
        ws.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.timeout_seconds < 1:
        parser.error("duration and timeout must be positive")
    report = run(args.duration_seconds, args.timeout_seconds)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ticks_observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
