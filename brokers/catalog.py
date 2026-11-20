"""Capability registry separating Forex brokers from crypto exchanges.

Metadata only: no adapter is instantiated, no credentials are read, and no
market data or orders are sent by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MarketDomain(StrEnum):
    FOREX = "forex"
    CRYPTO_SPOT = "crypto_spot"
    SYNTHETIC_INDICES = "synthetic_indices"
    CFD = "cfd"


@dataclass(frozen=True, slots=True)
class BrokerProfile:
    broker_id: str
    display_name: str
    domains: frozenset[MarketDomain]
    market_data_available: bool
    account_access_available: bool
    order_execution_available: bool
    integration_status: str
    execution_channel: str
    notes: str

    def supports(self, domain: MarketDomain) -> bool:
        return domain in self.domains


# Gate.io remains a separate crypto venue. Current Jarvis integration is
# read-only public crypto market observation/attestation.
GATEIO = BrokerProfile(
    broker_id="gateio",
    display_name="Gate.io",
    domains=frozenset({MarketDomain.CRYPTO_SPOT}),
    market_data_available=True,
    account_access_available=False,
    order_execution_available=False,
    integration_status="read_only_market_data",
    execution_channel="none",
    notes=(
        "Crypto spot exchange; not a conventional Forex broker. "
        "Never route Forex symbols or orders through Gate.io."
    ),
)

# Deriv is the selected Forex provider, via its MT5 platform. Its documented
# MT5 API manages account settings/accounts/payments but does not place MT5
# trades. MT5 trading is performed in the MT5 terminal, typically by an EA.
# This profile is intentionally not connected or execution-enabled.
DERIV_MT5_FOREX = BrokerProfile(
    broker_id="deriv_mt5",
    display_name="Deriv MT5",
    domains=frozenset({MarketDomain.FOREX, MarketDomain.CFD}),
    market_data_available=False,
    account_access_available=False,
    order_execution_available=False,
    integration_status="selected_not_connected",
    execution_channel="mt5_terminal_ea_required",
    notes=(
        "Selected provider for Forex CFDs subject to the user's account and "
        "instrument eligibility. Deriv MT5 APIs do not execute MT5 trades; "
        "a separately secured MT5 terminal/EA bridge is required. No feed, "
        "account or order route is connected by this catalog entry."
    ),
)

BROKER_CATALOG: dict[str, BrokerProfile] = {
    GATEIO.broker_id: GATEIO,
    DERIV_MT5_FOREX.broker_id: DERIV_MT5_FOREX,
}


def broker_for_domain(domain: MarketDomain) -> tuple[BrokerProfile, ...]:
    """Return catalog entries for a market domain without guessing."""
    return tuple(profile for profile in BROKER_CATALOG.values() if profile.supports(domain))


def validate_market_routing(*, broker_id: str, domain: MarketDomain) -> BrokerProfile:
    """Reject cross-domain routing and any profile without enabled execution."""
    try:
        profile = BROKER_CATALOG[broker_id]
    except KeyError as exc:
        raise ValueError(f"unknown broker profile: {broker_id}") from exc

    if not profile.supports(domain):
        raise ValueError(
            f"{profile.display_name} does not support the {domain.value} market domain"
        )
    if not profile.order_execution_available:
        raise RuntimeError(
            f"order execution is disabled for broker profile {profile.broker_id}"
        )
    return profile
