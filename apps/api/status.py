"""Minimal localhost-only read-only status API using the Python standard library."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Callable
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit


_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"
_STATIC_ASSETS = {
    "/dashboard": (_DASHBOARD_DIR / "index.html", "text/html; charset=utf-8"),
    "/dashboard.css": (_DASHBOARD_DIR / "dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": (_DASHBOARD_DIR / "dashboard.js", "text/javascript; charset=utf-8"),
    "/manifest.webmanifest": (_DASHBOARD_DIR / "manifest.webmanifest", "application/manifest+json"),
    "/service-worker.js": (_DASHBOARD_DIR / "service-worker.js", "text/javascript; charset=utf-8"),
    "/icon.svg": (_DASHBOARD_DIR / "icon.svg", "image/svg+xml"),
    "/icons/icon-192.png": (_DASHBOARD_DIR / "icons" / "icon-192.png", "image/png"),
    "/icons/icon-512.png": (_DASHBOARD_DIR / "icons" / "icon-512.png", "image/png"),
    "/icons/icon-maskable-512.png": (_DASHBOARD_DIR / "icons" / "icon-maskable-512.png", "image/png"),
    "/icons/apple-touch-icon.png": (_DASHBOARD_DIR / "icons" / "apple-touch-icon.png", "image/png"),
}


# Host names the API answers to. Browsers always send the Host header, so rejecting any other
# name stops DNS-rebinding pages from reading this localhost service. The port is ignored on
# purpose: STATUS_PORT is configurable. "jarvis" is the Compose service name the optional
# Telegram container uses to reach the health endpoint.
_ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1", "jarvis"})

_SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)


# The dashboard ships no inline script or style, so everything can be locked to same origin.
_DASHBOARD_CSP = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)


@lru_cache(maxsize=16)
def _showcase(seed: int, bars: int) -> bytes:
    from research.showcase import run_showcase

    return json.dumps(run_showcase(seed, bars), default=str).encode()


def _query_int(query: str, name: str, default: int) -> int:
    values = parse_qs(query).get(name)
    if not values:
        return default
    if not values[0].isdigit() or len(values[0]) > 10:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(values[0])


def host_header_allowed(value: str | None) -> bool:
    """Return True when a Host header names one of the allowed local hostnames."""
    if not value:
        return False
    value = value.strip().lower()
    if value.startswith("["):
        # Bracketed IPv6 literal, optionally followed by :port.
        end = value.find("]")
        hostname = value[1:end] if end != -1 else ""
    else:
        hostname = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    return hostname in _ALLOWED_HOSTNAMES


class StatusHandler(BaseHTTPRequestHandler):
    status_provider: Callable[[], dict] = lambda: {}

    def end_headers(self) -> None:
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    def do_GET(self) -> None:
        if not host_header_allowed(self.headers.get("Host")):
            self.send_error(403, "Forbidden host")
            return

        # Route on the path alone: an installed PWA may be launched with a query string
        # (for example /dashboard?source=pwa), and routing the raw target would 404 it.
        parts = urlsplit(self.path)
        route = parts.path
        if route in _STATIC_ASSETS:
            asset_path, content_type = _STATIC_ASSETS[route]
            try:
                body = asset_path.read_bytes()
            except OSError:
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            if content_type.startswith("text/html"):
                self.send_header("Content-Security-Policy", _DASHBOARD_CSP)
            self.end_headers()
            self.wfile.write(body)
            return

        if route not in {"/", "/health", "/status", "/self-check", "/features", "/gate", "/showcase"}:
            self.send_error(404)
            return

        try:
            if route == "/health":
                payload = {"ok": True}
            elif route == "/features":
                from core.feature_registry import feature_state_inventory
                payload = feature_state_inventory()
            elif route == "/gate":
                from research.showcase import gate_payload
                payload = gate_payload()
            elif route == "/showcase":
                from research.showcase import DEFAULT_BARS, DEFAULT_SEED
                try:
                    seed = _query_int(parts.query, "seed", DEFAULT_SEED)
                    bars = _query_int(parts.query, "bars", DEFAULT_BARS)
                    body = _showcase(seed, bars)
                except ValueError as exc:
                    self.send_error(400, str(exc)[:80])
                    return
                payload = None
            elif route == "/self-check":
                payload = {"ok": True, "status": "healthy", "mode": "paper", "kill_switch": True}
            elif route == "/":
                payload = {
                    "ok": True,
                    "service": "jarvis-unified",
                    "status": "paper",
                    "routes": [
                        "/health",
                        "/status",
                        "/self-check",
                        "/features",
                        "/gate",
                        "/showcase",
                        "/dashboard",
                    ],
                }
                provider_payload = self.status_provider()
                if isinstance(provider_payload, dict):
                    payload.update(provider_payload)
            else:
                payload = self.status_provider()
            if payload is not None:
                body = json.dumps(payload, default=str).encode()
        except Exception:
            # Never leak a traceback or internals to the client; the server keeps running.
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve(
    host: str,
    port: int,
    status_provider: Callable[[], dict],
    *,
    allow_container_bind: bool = False,
) -> None:
    if host not in {"127.0.0.1", "localhost"} and not (
        allow_container_bind and host == "0.0.0.0"
    ):
        raise ValueError("Status API may only bind to localhost")
    handler = type("BoundStatusHandler", (StatusHandler,), {"status_provider": staticmethod(status_provider)})
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise RuntimeError(f"Status API could not bind to {host}:{port}: {exc.strerror or exc}") from exc
    server.serve_forever()
