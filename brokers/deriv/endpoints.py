"""Strict endpoint selection helpers. Never log or persist OTP values."""
from __future__ import annotations

from urllib.parse import urlsplit


DEMO_WS_HOST = "api.derivws.com"
DEMO_WS_PATH = "/trading/v1/options/ws/demo"


def validate_demo_websocket_url(url: str) -> str:
    """Return the URL only when it is the exact Deriv demo WebSocket endpoint."""
    if not isinstance(url, str) or not url:
        raise ValueError("demo WebSocket URL is required")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "wss"
        or parsed.hostname != DEMO_WS_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != DEMO_WS_PATH
        or parsed.fragment
        or not parsed.query
        or parsed.query.count("=") < 1
        or "otp" not in {part.split("=", 1)[0] for part in parsed.query.split("&") if "=" in part}
    ):
        raise ValueError("only the exact Deriv demo WebSocket endpoint with an OTP is allowed")
    return url
