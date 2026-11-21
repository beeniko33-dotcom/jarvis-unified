import unittest
from pathlib import Path


class JaeoBrowserAuditContractTests(unittest.TestCase):
    def test_approval_queue_displays_decision_audit_metadata(self):
        page = Path("apps/portal/jaeo.html").read_text(encoding="utf-8")
        self.assertIn("Decision by:", page)
        self.assertIn("Decision reason:", page)
        self.assertIn("requested_at", page)
        self.assertIn("decided_at", page)
        self.assertIn("decided_by_user_id", page)
        self.assertIn("decision_reason", page)
        self.assertIn("Decision recorded. No external action was executed.", page)

    def test_owner_grant_keeps_the_audit_id_visible(self):
        page = Path("apps/portal/jaeo.html").read_text(encoding="utf-8")
        self.assertLess(page.index("await loadOperatorUsers();", page.index("async function grantOperator")),
                        page.index("Audit record:", page.index("async function grantOperator")))

    def test_browser_e2e_is_manual_and_hard_scoped_to_qa(self):
        workflow = Path(".github/workflows/qa-browser-e2e.yml").read_text(encoding="utf-8")
        runner = Path("scripts/qa_browser_e2e.py").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("JARVIS_SUPABASE_SERVICE_ROLE_KEY", workflow)
        self.assertIn("https://guvszwxvmitdvykvtsnc.supabase.co", runner)
        self.assertIn("Control-panel page is not connected to the isolated QA project", runner)
        self.assertIn("JAEO page is not connected to the isolated QA project", runner)
        self.assertIn("finally:", runner)
        self.assertIn("qa.set_roles", runner)


if __name__ == "__main__":
    unittest.main()
