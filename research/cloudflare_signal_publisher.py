"""One-way publisher that sends paper-trading signal events to the Jarvis Cloudflare worker.

POSTs to <worker>/signals with the collector bearer token (JARVIS_COLLECTOR_TOKEN). The worker
validates and forwards to Supabase, where rows are stored research_only with no evidence credit.
The token is never logged or put in an error message. Nothing here can place or authorize an order.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def build_signal_body(kind: str, ts: str, symbol: str, interval: str, payload: dict, *,
                      entries_allowed: bool) -> dict:
    """Map one runner event to the /signals schema. Only whitelisted, non-secret fields are sent."""
    side: str | None = None
    body: dict[str, Any] = {"kind": "", "entries_allowed": entries_allowed}
    if kind == "observation":
        body["kind"], side = "signal", payload["signal"]
        body.update(price=payload["close"], fast_sma=payload["fast_sma"], slow_sma=payload["slow_sma"])
    elif kind == "entry_fill":
        body["kind"], side = "paper_fill", "buy"
        body.update(price=payload["price"], quantity=payload["quantity"])
    elif kind == "exit_fill":
        body["kind"], side = "paper_fill", "sell"
        body.update(price=payload["price"], quantity=payload["quantity"], net_pnl=payload["realized_net_pnl"])
    elif kind == "risk_reject":
        body["kind"] = "risk_reject"
        body.update(price=payload.get("price", "0"), reason=str(payload.get("reason", ""))[:64])
    else:
        raise ValueError("unsupported event kind")
    body.update(
        side=side, symbol=symbol, interval=interval, event_time=ts,
        strategy_id=payload.get("strategy_id", "sma-crossover-long"),
        strategy_version=payload.get("strategy_version", "1.0.0"),
        idempotency_key=f"jarvis-live:{symbol}:{interval}:{ts}:{body['kind']}:{side or 'none'}",
    )
    return body


class CloudflareSignalPublisher:
    def __init__(self, base_url: str, token: str, *, opener: Callable = urlopen, timeout: float = 15) -> None:
        parts = urlsplit(base_url.strip())
        local = parts.hostname in {"127.0.0.1", "localhost"}
        if parts.scheme != "https" and not (parts.scheme == "http" and local):
            raise ValueError("JARVIS_WORKER_URL must be an https URL (http only for localhost)")
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("JARVIS_WORKER_URL must be a plain worker URL without credentials or query")
        if not token.strip():
            raise ValueError("JARVIS_COLLECTOR_TOKEN must be configured")
        self._url = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}/signals"
        self._token, self._opener, self._timeout = token.strip(), opener, timeout

    @classmethod
    def from_env(cls, url: str | None = None) -> "CloudflareSignalPublisher":
        return cls(url or os.getenv("JARVIS_WORKER_URL", ""), os.getenv("JARVIS_COLLECTOR_TOKEN", ""))

    def publish(self, body: dict) -> None:
        """Deliver one event or raise RuntimeError (never containing the token or response body)."""
        request = Request(
            self._url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._token,
                     "User-Agent": "JarvisUnified-signal-runner/1.0"})
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = getattr(response, "status", 200)
                if status not in (200, 202):
                    raise RuntimeError(f"Jarvis worker returned HTTP {status}")
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise RuntimeError(f"Jarvis worker rejected the signal with HTTP {code}") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Jarvis worker could not be reached") from None
