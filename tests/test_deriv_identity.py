from __future__ import annotations

import pytest

from brokers.deriv.identity import DemoIdentityError, parse_demo_account_claim

TEST_FINGERPRINT_KEY = b'test-only-fingerprint-key-32-bytes!!'


def authorize_response(**overrides):
    response = {
        "loginid": "VR123456",
        "is_virtual": 1,
        "account_list": [
            {
                "loginid": "VR123456",
                "account_type": "trading",
                "is_virtual": 1,
                "is_disabled": 0,
                "currency": "USD",
                "landing_company_name": "virtual",
            }
        ],
    }
    response.update(overrides)
    return response


def test_accepts_only_explicit_selected_virtual_trading_account():
    claim = parse_demo_account_claim(authorize_response(), fingerprint_key=TEST_FINGERPRINT_KEY)
    assert claim.claim_status == "PROVIDER_CLAIMED_DEMO_UNVERIFIED"
    assert claim.provider_authenticity_verified is False
    assert claim.evidence_eligible is False
    assert claim.currency == "USD"
    assert claim.landing_company_name == "virtual"
    assert len(claim.account_fingerprint) == 64
    assert "VR123456" not in repr(claim)


@pytest.mark.parametrize("value", [0, None, True, "1"])
def test_rejects_non_demo_or_malformed_top_level_virtual_flag(value):
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(authorize_response(is_virtual=value), fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_real_selected_account_even_if_other_demo_account_exists():
    response = authorize_response(
        is_virtual=0,
        account_list=[
            {
                "loginid": "CR123456",
                "account_type": "trading",
                "is_virtual": 0,
                "is_disabled": 0,
                "currency": "USD",
                "landing_company_name": "svg",
            },
            {
                "loginid": "VR123456",
                "account_type": "trading",
                "is_virtual": 1,
                "is_disabled": 0,
                "currency": "USD",
                "landing_company_name": "virtual",
            },
        ],
    )
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_selected_account_missing_from_account_list():
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(authorize_response(account_list=[]), fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_duplicate_selected_loginid():
    response = authorize_response()
    response["account_list"].append(dict(response["account_list"][0]))
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("is_virtual", 0),
        ("is_virtual", True),
        ("is_disabled", 1),
        ("is_disabled", False),
    ],
)
def test_rejects_selected_account_flag_mismatch(field, value):
    response = authorize_response()
    response["account_list"][0][field] = value
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_non_trading_account():
    response = authorize_response()
    response["account_list"][0]["account_type"] = "wallet"
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_malformed_selected_account_metadata():
    response = authorize_response()
    response["account_list"][0]["currency"] = ""
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_malformed_or_missing_selected_loginid():
    for loginid in (None, "", "VR-123", "CR123456"):
        with pytest.raises(DemoIdentityError):
            parse_demo_account_claim(authorize_response(loginid=loginid), fingerprint_key=TEST_FINGERPRINT_KEY)


def test_rejects_non_object_authorization_response():
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(None, fingerprint_key=TEST_FINGERPRINT_KEY)


def test_fingerprint_is_keyed_and_changes_with_key():
    response = authorize_response()
    first = parse_demo_account_claim(response, fingerprint_key=TEST_FINGERPRINT_KEY)
    second = parse_demo_account_claim(response, fingerprint_key=b"another-test-key-that-is-at-least-32-bytes")
    assert first.account_fingerprint != second.account_fingerprint


@pytest.mark.parametrize("key", [None, b"", b"too-short"])
def test_rejects_missing_or_weak_fingerprint_key(key):
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(authorize_response(), fingerprint_key=key)
