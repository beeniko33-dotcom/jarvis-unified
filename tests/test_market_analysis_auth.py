"""Guard the Gate.io collector's machine-key compatibility boundary."""
from pathlib import Path
import unittest


SOURCE = Path("supabase/functions/market-analysis/index.ts").read_text(encoding="utf-8")


class MarketAnalysisAuthCompatibilityTests(unittest.TestCase):
    def test_accepts_both_current_and_legacy_server_key_sources(self):
        self.assertIn("SECRET_KEYS.default", SOURCE)
        self.assertIn('Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")', SOURCE)
        self.assertIn('Deno.env.get("SERVICE_ROLE_KEY")', SOURCE)
        self.assertIn("const SERVICE_ROLE_KEY = SERVICE_ROLE_KEYS[0] ?? \"\";", SOURCE)

    def test_machine_auth_checks_all_configured_service_keys(self):
        self.assertIn("SERVICE_ROLE_KEYS.some((key) => tokenMatches(suppliedApiKey, key))", SOURCE)
        self.assertIn('req.headers.get("x-jarvis-ingest-token")', SOURCE)

    def test_malformed_secret_key_json_fails_closed_without_crashing_module_load(self):
        self.assertIn("try {\n  SECRET_KEYS = JSON.parse", SOURCE)
        self.assertIn("} catch {\n  SECRET_KEYS = {};", SOURCE)


if __name__ == "__main__":
    unittest.main()
