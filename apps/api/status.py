"""Minimal localhost-only read-only status API using the Python standard library."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Callable

class StatusHandler(BaseHTTPRequestHandler):
    status_provider: Callable[[], dict] = lambda: {}

    def do_GET(self) -> None:
        if self.path not in {"/", "/health", "/status", "/self-check", "/features"}:
            self.send_error(404)
            return

        if self.path == "/health":
            payload = {"ok": True}
        elif self.path == "/features":
            from core.feature_registry import feature_state_inventory
            payload = feature_state_inventory()
        elif self.path == "/self-check":
            payload = {"ok": True, "status": "healthy", "mode": "paper", "kill_switch": True}
        elif self.path == "/":
            payload = {
                "ok": True,
                "service": "jarvis-unified",
                "status": "paper",
                "routes": ["/health", "/status", "/self-check", "/features"],
            }
            provider_payload = self.status_provider()
            if isinstance(provider_payload, dict):
                payload.update(provider_payload)
        else:
            payload = self.status_provider()

        body = json.dumps(payload, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt: str, *args: object) -> None:
        return

def serve(host: str, port: int, status_provider: Callable[[], dict]) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Status API may only bind to localhost")
    handler = type("BoundStatusHandler", (StatusHandler,), {"status_provider": staticmethod(status_provider)})
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise RuntimeError(f"Status API could not bind to {host}:{port}: {exc.strerror or exc}") from exc
    server.serve_forever()
