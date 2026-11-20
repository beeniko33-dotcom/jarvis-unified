from __future__ import annotations

import unittest

from brokers.catalog import (
    BROKER_CATALOG,
    DERIV_MT5_FOREX,
    GATEIO,
    MarketDomain,
    broker_for_domain,
    validate_market_routing,
)


class BrokerCatalogTests(unittest.TestCase):
    def test_gateio_is_crypto_spot_not_forex(self):
        self.assertTrue(GATEIO.supports(MarketDomain.CRYPTO_SPOT))
        self.assertFalse(GATEIO.supports(MarketDomain.FOREX))
        self.assertFalse(GATEIO.order_execution_available)

    def test_deriv_mt5_is_selected_for_forex_but_not_connected(self):
        self.assertTrue(DERIV_MT5_FOREX.supports(MarketDomain.FOREX))
        self.assertTrue(DERIV_MT5_FOREX.supports(MarketDomain.CFD))
        self.assertEqual(DERIV_MT5_FOREX.integration_status, "selected_not_connected")
        self.assertEqual(DERIV_MT5_FOREX.execution_channel, "mt5_terminal_ea_required")
        self.assertFalse(DERIV_MT5_FOREX.market_data_available)
        self.assertFalse(DERIV_MT5_FOREX.account_access_available)
        self.assertFalse(DERIV_MT5_FOREX.order_execution_available)
        self.assertEqual(broker_for_domain(MarketDomain.FOREX), (DERIV_MT5_FOREX,))

    def test_cross_domain_gateio_forex_routing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not support the forex"):
            validate_market_routing(broker_id="gateio", domain=MarketDomain.FOREX)

    def test_selected_deriv_profile_cannot_execute_until_bridge_is_verified(self):
        with self.assertRaisesRegex(RuntimeError, "execution is disabled"):
            validate_market_routing(broker_id="deriv_mt5", domain=MarketDomain.FOREX)

    def test_unknown_broker_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown broker profile"):
            validate_market_routing(
                broker_id="unverified-provider",
                domain=MarketDomain.FOREX,
            )

    def test_no_profile_is_execution_enabled(self):
        self.assertTrue(BROKER_CATALOG)
        self.assertFalse(any(p.order_execution_available for p in BROKER_CATALOG.values()))


if __name__ == "__main__":
    unittest.main()
