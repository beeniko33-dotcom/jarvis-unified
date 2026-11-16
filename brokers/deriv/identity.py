"""Fail-closed parsing of Deriv's authorize account identity claims.

This module validates response fields only. It does not authenticate the
transport, prove provider origin, or make the resulting claim eligible evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import re
from typing import Any, Mapping


_LOGIN_ID = re.compile(r"^[A-Z0-9]{4,32}$")


class DemoIdentityError(ValueError):
    """Authorization response is missing, ambiguous, or not explicitly demo."""


@dataclass(frozen=True)
class DerivDemoAccountClaim:
    """Redacted provider-claimed demo identity; never an authentication verdict."""

    account_fingerprint: str
    currency: str
    landing_company_name: str
    claim_status: str = "PROVIDER_CLAIMED_DEMO_UNVERIFIED"
    provider_authenticity_verified: bool = False
    evidence_eligible: bool = False


def _flag(payload: Mapping[str, Any], field: str, expected: int) -> None:
    value = payload.get(field)
    # bool is a subclass of int in Python; reject it to avoid accepting True/False
    # where the provider schema explicitly represents numeric flags.
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise DemoIdentityError(f"authorization response has invalid {field}")


def parse_demo_account_claim(
    authorization: Mapping[str, Any],
    *,
    fingerprint_key: bytes,
) -> DerivDemoAccountClaim:
    """Parse an authorize response and require one unambiguous virtual trading account.

    The caller must separately establish a verified TLS session and successful
    authorization exchange. Even then, this parser's output remains an unverified
    provider claim until an independent verification layer is implemented.
    """
    if not isinstance(fingerprint_key, bytes) or len(fingerprint_key) < 32:
        raise DemoIdentityError("fingerprint_key must contain at least 32 secret bytes")
    if not isinstance(authorization, Mapping):
        raise DemoIdentityError("authorization response must be an object")

    selected_loginid = authorization.get("loginid")
    if (
        not isinstance(selected_loginid, str)
        or not _LOGIN_ID.fullmatch(selected_loginid)
    ):
        raise DemoIdentityError("authorization response has invalid selected loginid")

    _flag(authorization, "is_virtual", 1)

    accounts = authorization.get("account_list")
    if not isinstance(accounts, list) or not accounts:
        raise DemoIdentityError("authorization response has no account_list")

    matches: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for account in accounts:
        if not isinstance(account, Mapping):
            raise DemoIdentityError("authorization account entry is malformed")
        loginid = account.get("loginid")
        if not isinstance(loginid, str) or not _LOGIN_ID.fullmatch(loginid):
            raise DemoIdentityError("authorization account entry has invalid loginid")
        if loginid in seen:
            raise DemoIdentityError("authorization account_list contains duplicate loginid")
        seen.add(loginid)
        if loginid == selected_loginid:
            matches.append(account)

    if len(matches) != 1:
        raise DemoIdentityError("selected account is missing or ambiguous")

    selected = matches[0]
    if selected.get("account_type") != "trading":
        raise DemoIdentityError("selected account is not a trading account")
    _flag(selected, "is_virtual", 1)
    _flag(selected, "is_disabled", 0)

    currency = selected.get("currency")
    landing_company = selected.get("landing_company_name")
    if (
        not isinstance(currency, str)
        or not re.fullmatch(r"[A-Z0-9]{2,12}", currency)
        or not isinstance(landing_company, str)
        or not re.fullmatch(r"[a-z0-9_-]{2,64}", landing_company)
    ):
        raise DemoIdentityError("selected account metadata is incomplete or malformed")

    fingerprint = hmac.new(fingerprint_key, selected_loginid.encode("ascii"), digestmod="sha256").hexdigest()
    return DerivDemoAccountClaim(
        account_fingerprint=fingerprint,
        currency=currency,
        landing_company_name=landing_company,
    )
