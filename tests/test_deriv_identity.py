from __future__ import annotations

import pytest

from brokers.deriv.identity import DemoIdentityError, parse_demo_account_claim


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
    claim = parse_demo_account_claim(authorize_response())
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
        parse_demo_account_claim(authorize_response(is_virtual=value))


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
        parse_demo_account_claim(response)


def test_rejects_selected_account_missing_from_account_list():
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(authorize_response(account_list=[]))


def test_rejects_duplicate_selected_loginid():
    response = authorize_response()
    response["account_list"].append(dict(response["account_list"][0]))
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response)


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
        parse_demo_account_claim(response)


def test_rejects_non_trading_account():
    response = authorize_response()
    response["account_list"][0]["account_type"] = "wallet"
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response)


def test_rejects_malformed_selected_account_metadata():
    response = authorize_response()
    response["account_list"][0]["currency"] = ""
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(response)


def test_rejects_malformed_or_missing_selected_loginid():
    for loginid in (None, "", "VR-123", "CR123456"):
        with pytest.raises(DemoIdentityError):
            parse_demo_account_claim(authorize_response(loginid=loginid))


def test_rejects_non_object_authorization_response():
    with pytest.raises(DemoIdentityError):
        parse_demo_account_claim(None)
