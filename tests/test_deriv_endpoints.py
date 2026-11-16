from __future__ import annotations

import pytest

from brokers.deriv.endpoints import validate_demo_websocket_url


VALID = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=opaque-token"


def test_accepts_exact_demo_endpoint_with_one_otp():
    assert validate_demo_websocket_url(VALID) == VALID


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "ws://api.derivws.com/trading/v1/options/ws/demo?otp=x",
        "wss://api.derivws.com/trading/v1/options/ws/live?otp=x",
        "wss://api.derivws.com.evil.test/trading/v1/options/ws/demo?otp=x",
        "wss://api.derivws.com:443/trading/v1/options/ws/demo?otp=x",
        "wss://user:pass@api.derivws.com/trading/v1/options/ws/demo?otp=x",
        "wss://api.derivws.com/trading/v1/options/ws/demo",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x&otp=y",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x&app_id=123",
        "wss://api.derivws.com/trading/v1/options/ws/demo?token=x",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x#fragment",
        "wss://[malformed/trading/v1/options/ws/demo?otp=x",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=%",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=%ZZ",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=%2",
        "wss://api.derivws.com/trading/v1/options/ws/demo?otp=%FF",
        " wss://api.derivws.com/trading/v1/options/ws/demo?otp=x",
    ],
)
def test_rejects_endpoint_variants_and_ambiguous_query(url):
    with pytest.raises(ValueError):
        validate_demo_websocket_url(url)
