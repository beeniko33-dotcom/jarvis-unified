from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class JaeoPortalConsoleContractTests(unittest.TestCase):
    def test_console_uses_authenticated_qa_edge_function(self):
        page = (ROOT / "apps/portal/jaeo.html").read_text(encoding="utf-8")
        config = (ROOT / "apps/portal/jaeo-config.js").read_text(encoding="utf-8")
        self.assertIn("@supabase/supabase-js@2.119.2", page)
        self.assertIn("signInWithPassword", page)
        self.assertIn("emailRedirectTo:window.location.origin+\"/jaeo.html\"", page)
        self.assertIn("supabase.auth.signUp", page)
        self.assertIn("/functions/v1/jaeo-operator", page)
        self.assertIn('"Bearer "+session.access_token', page)
        self.assertIn('operation:"list_approvals"', page)
        self.assertIn('operation:"decide_approval"', page)
        self.assertIn("JAEO_BOOTSTRAP_OWNER_USER_ID", page)
        self.assertNotIn('value="change_secret"', page)
        self.assertIn("sb_publishable_", config)
        self.assertIn("guvszwxvmitdvykvtsnc.supabase.co", config)
        self.assertNotIn("sb_secret_", config)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", config)

    def test_console_discloses_non_execution_boundary(self):
        page = (ROOT / "apps/portal/jaeo.html").read_text(encoding="utf-8").lower()
        self.assertIn("run code", page)
        self.assertIn("does not execute", page)
        self.assertIn("production", page)
        self.assertIn("trading", page)
        self.assertNotIn("change_secret", page)


if __name__ == "__main__":
    unittest.main()
