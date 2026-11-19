from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class TestMarketAnalysisMachineAuth(unittest.TestCase):
    def test_handler_verifies_users_and_machine_collectors(self):
        source = (ROOT / "supabase" / "functions" / "market-analysis" / "index.ts").read_text()
        config = (ROOT / "supabase" / "config.toml").read_text()

        self.assertIn("[functions.market-analysis]", config)
        self.assertIn("verify_jwt = false", config.split("[functions.market-analysis]", 1)[1])
        self.assertIn("x-jarvis-ingest-token", source)
        self.assertIn("tokenMatches", source)
        self.assertIn('"/auth/v1/user"', source)
        self.assertIn("isAllowlistedOperator(userId)", source)
        self.assertNotIn("jwtClaims", source)
        self.assertIn("order_authorized: false", source)
        self.assertIn("live_execution: false", source)
