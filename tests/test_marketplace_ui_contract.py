import unittest
from html.parser import HTMLParser
from pathlib import Path


class MarketplaceScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.current_type = ""
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.in_script = True
            self.current_type = dict(attrs).get("type", "")

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self.in_script = False
            self.current_type = ""

    def handle_data(self, data):
        if self.in_script and self.current_type == "module":
            self.scripts.append(data)


class MarketplaceUiContractTests(unittest.TestCase):
    def test_order_function_uses_current_supabase_sdk_for_secret_key_compatibility(self):
        source = Path("supabase/functions/marketplace-orders/index.ts").read_text(encoding="utf-8")
        self.assertIn("npm:@supabase/supabase-js@2.119.2", source)
        self.assertNotIn("@2.45.4", source)

    def test_inline_module_has_real_line_breaks(self):
        page = Path("apps/control_panel/marketplace.html").read_text(encoding="utf-8")
        parser = MarketplaceScripts()
        parser.feed(page)
        module = "\n".join(parser.scripts)
        self.assertTrue(module.strip(), "Marketplace module script must exist")
        self.assertNotIn("\\n", module, "Literal escaped newline breaks JavaScript between statements")

    def test_backend_configuration_is_external_and_public_key_only(self):
        page = Path("apps/control_panel/marketplace.html").read_text(encoding="utf-8")
        self.assertIn('./jarvis-config.js', page)
        self.assertIn("supabasePublishableKey", page)
        config = Path("apps/control_panel/jarvis-config.js").read_text(encoding="utf-8")
        config_code = "\\n".join(line for line in config.splitlines() if not line.lstrip().startswith("//"))
        self.assertIn("https://guvszwxvmitdvykvtsnc.supabase.co", config_code)
        self.assertIn("sb_publishable_", config_code)
        self.assertNotIn("service_role", config_code.lower())
        self.assertNotIn("sb_secret_", config_code)
        self.assertNotIn("service_role", page.lower())
        self.assertNotIn("sb_secret_", page)

    def test_order_intent_requires_user_session(self):
        page = Path("apps/control_panel/marketplace.html").read_text(encoding="utf-8")
        self.assertIn('authorization:"Bearer "+token', page)
        self.assertIn('"/functions/v1/marketplace-orders"', page)
        self.assertIn("No payment was taken and no reward was issued", page)
        self.assertIn("sb.auth.signInWithPassword", page)
        self.assertIn("isolated Jarvis QA", page)
        self.assertIn('show("signin",false)', page)



class CareerUiContractTests(unittest.TestCase):
    def test_career_uses_shared_qa_configuration_and_fails_closed(self):
        page = Path("apps/control_panel/career.html").read_text(encoding="utf-8")
        self.assertIn('./jarvis-config.js', page)
        self.assertIn('window.JARVIS_CONFIG', page)
        self.assertIn('Missing JARVIS_CONFIG', page)
        self.assertNotIn("service_role", page.lower())
        self.assertNotIn("sb_secret_", page)

    def test_employer_verification_gates_job_publishing(self):
        page = Path("apps/control_panel/career.html").read_text(encoding="utf-8")
        self.assertIn('id="create-job" class="primary" disabled', page)
        self.assertIn('Job publishing remains locked', page)
        self.assertIn('verification_status', page)

    def test_applications_and_messages_use_authenticated_user_records(self):
        page = Path("apps/control_panel/career.html").read_text(encoding="utf-8")
        self.assertIn('career_applications', page)
        self.assertIn('candidate_id:user.id', page)
        self.assertIn('career_conversations', page)
        self.assertIn('career_messages', page)
        self.assertIn('sender_id:user.id', page)
        self.assertIn("sb.auth.signInWithPassword", page)
        self.assertIn("isolated Jarvis QA", page)
        self.assertIn('show("signin",false)', page)


if __name__ == "__main__":
    unittest.main()
