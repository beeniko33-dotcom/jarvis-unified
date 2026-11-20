from __future__ import annotations

import unittest

from brokers.catalog import (
    BROKER_CATALOG,
    GATEIO,
    MT5_FOREX_TEMPLATE,
    MarketDomain,
    broker_for_domain,
    validate_market_routing,
)


class BrokerCatalogTests(unittest.TestCase):
    def test_gateio_is_crypto_spot_not_forex(self):
        self.assertTrue(GATEIO.supports(MarketDomain.CRYPTO_SPOT))
        self.assertFalse(GATEIO.supports(MarketDomain.FOREX))
        self.assertFalse(GATEIO.order_execution_available)

    def test_forex_catalog_does_not_invent_a_connected_broker(self):
        forex_profiles = broker_for_domain(MarketDomain.FOREX)
        self.assertEqual(forex_profiles, (MT5_FOREX_TEMPLATE,))
        self.assertEqual(MT5_FOREX_TEMPLATE.integration_status, "not_configured")
        self.assertFalse(MT5_FOREX_TEMPLATE.market_data_available)
        self.assertFalse(MT5_FOREX_TEMPLATE.order_execution_available)

    def test_cross_domain_gateio_forex_routing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not support the forex"):
            validate_market_routing(
                broker_id="gateio",
                domain=MarketDomain.FOREX,
            )

    def test_known_but_disabled_forex_template_cannot_execute(self):
        with self.assertRaisesRegex(RuntimeError, "execution is disabled"):
            validate_market_routing(
                broker_id="mt5_forex_template",
                domain=MarketDomain.FOREX,
            )

    def test_unknown_broker_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown broker profile"):
            validate_market_routing(
                broker_id="unverified-provider",
                domain=MarketDomain.FOREX,
            )

    def test_catalog_has_no_execution_enabled_profile(self):
        self.assertTrue(BROKER_CATALOG)
        self.assertFalse(any(p.order_execution_available for p in BROKER_CATALOG.values()))


if __name__ == "__main__":
    unittest.main()
