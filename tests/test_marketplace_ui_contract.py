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
        self.assertIn("https://guvszwxvmitdvykvtsnc.supabase.co", config)
        self.assertIn("sb_publishable_", config)
        self.assertNotIn("service_role", config.lower())
        self.assertNotIn("sb_secret_", config)
        self.assertNotIn("service_role", page.lower())
        self.assertNotIn("sb_secret_", page)

    def test_order_intent_requires_user_session(self):
        page = Path("apps/control_panel/marketplace.html").read_text(encoding="utf-8")
        self.assertIn('authorization:"Bearer "+token', page)
        self.assertIn('"/functions/v1/marketplace-orders"', page)
        self.assertIn("No payment was taken and no reward was issued", page)


if __name__ == "__main__":
    unittest.main()
