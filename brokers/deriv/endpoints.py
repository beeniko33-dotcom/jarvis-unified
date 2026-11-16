"""Strict endpoint selection helpers. Never log or persist OTP values."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit


DEMO_WS_HOST = "api.derivws.com"
DEMO_WS_PATH = "/trading/v1/options/ws/demo"


def validate_demo_websocket_url(url: str) -> str:
    """Return the URL only for the exact demo endpoint with one non-empty OTP."""
    if not isinstance(url, str) or not url:
        raise ValueError("demo WebSocket URL is required")
    parsed = None
    try:
        parsed = urlsplit(url)
        # Parse strictly and require exactly one parameter. This prevents extra
        # query controls, duplicate OTP ambiguity, and blank OTP values.
        query_items = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
        valid_otp = len(query_items) == 1 and query_items[0][0] == "otp" and bool(query_items[0][1])
        valid_port = parsed.port is None
    except ValueError:
        valid_otp = False
        valid_port = False

    if (
        parsed is None
        or parsed.scheme != "wss"
        or parsed.hostname != DEMO_WS_HOST
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != DEMO_WS_PATH
        or parsed.fragment
        or not valid_otp
    ):
        raise ValueError("only the exact Deriv demo WebSocket endpoint with one non-empty OTP is allowed")
    return url
