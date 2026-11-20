"""Capability registry separating Forex brokers from crypto exchanges.

This is descriptive metadata only. It does not instantiate an adapter, access
credentials, fetch quotes, or enable order execution.
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
    notes: str

    def supports(self, domain: MarketDomain) -> bool:
        return domain in self.domains


# Gate.io remains a separate crypto venue. The existing Jarvis integration is
# read-only market observation/attestation; no exchange order adapter is enabled.
GATEIO = BrokerProfile(
    broker_id="gateio",
    display_name="Gate.io",
    domains=frozenset({MarketDomain.CRYPTO_SPOT}),
    market_data_available=True,
    account_access_available=False,
    order_execution_available=False,
    integration_status="read_only_market_data",
    notes=(
        "Crypto spot exchange; not a conventional Forex broker. "
        "Do not map FX symbols to Gate.io markets or route Forex orders here."
    ),
)

# A future MT5-compatible provider can be added only after the operator selects
# and verifies a named broker, supported account region, demo access and API.
MT5_FOREX_TEMPLATE = BrokerProfile(
    broker_id="mt5_forex_template",
    display_name="MT5-compatible Forex broker (not selected)",
    domains=frozenset({MarketDomain.FOREX}),
    market_data_available=False,
    account_access_available=False,
    order_execution_available=False,
    integration_status="not_configured",
    notes=(
        "Template only. No broker has been selected or connected; no quotes, "
        "accounts, or order execution are available through this profile."
    ),
)

BROKER_CATALOG: dict[str, BrokerProfile] = {
    GATEIO.broker_id: GATEIO,
    MT5_FOREX_TEMPLATE.broker_id: MT5_FOREX_TEMPLATE,
}


def broker_for_domain(domain: MarketDomain) -> tuple[BrokerProfile, ...]:
    """Return configured catalog entries for a market domain, without guessing."""
    return tuple(profile for profile in BROKER_CATALOG.values() if profile.supports(domain))


def validate_market_routing(*, broker_id: str, domain: MarketDomain) -> BrokerProfile:
    """Reject cross-domain routing and profiles without an execution adapter."""
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
