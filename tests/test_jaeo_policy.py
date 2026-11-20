from __future__ import annotations

import unittest

from research.jaeo_policy import (
    Action, Decision, evaluate_action, feedback_event, validate_task,
)


class JaeoPolicyTests(unittest.TestCase):
    def test_safe_inspection_and_test_are_allowed(self):
        for action in (Action.INSPECT.value, Action.TEST.value, Action.CREATE_BRANCH.value):
            result = evaluate_action(agent="engineering", action=action, resource_id="jarvis-preview")
            self.assertEqual(result.decision, Decision.ALLOW)
            self.assertEqual(result.mode, "paper")
            self.assertFalse(result.live_trading_enabled)

    def test_mutations_require_human_approval(self):
        for action in (
            Action.CHANGE_CODE.value, Action.CHANGE_SCHEMA.value,
            Action.PROVISION_RESOURCE.value, Action.CREATE_CRON.value,
            Action.DEPLOY_PREVIEW.value, Action.MERGE_PULL_REQUEST.value,
        ):
            result = evaluate_action(agent="engineering", action=action, resource_id="preview")
            self.assertEqual(result.decision, Decision.APPROVAL_REQUIRED)
            self.assertTrue(result.requires_human_approval)

    def test_explicit_approval_only_authorizes_approvable_action(self):
        result = evaluate_action(agent="database", action=Action.CHANGE_SCHEMA.value,
                                 resource_id="isolated-prototype", approval_granted=True)
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_critical_actions_are_never_authorized(self):
        for action in (
            Action.LIVE_TRADE.value, Action.DEPLOY_PRODUCTION.value,
            Action.CHANGE_OPERATOR_CONTROLS.value,
        ):
            result = evaluate_action(agent="release", action=action, approval_granted=True)
            self.assertEqual(result.decision, Decision.DENY)

    def test_production_resources_are_denied(self):
        for resource in (
            "zythldptlplyutphgxpg", "db.zythldptlplyutphgxpg.supabase.co",
            "jarvis-control-worker", "production",
        ):
            result = evaluate_action(agent="infrastructure", action=Action.INSPECT.value,
                                     resource_id=resource)
            self.assertEqual(result.decision, Decision.DENY)

    def test_unknown_agent_and_action_fail_closed(self):
        self.assertEqual(evaluate_action(agent="root", action="inspect").decision, Decision.DENY)
        self.assertEqual(evaluate_action(agent="audit", action="shell").decision, Decision.DENY)

    def test_task_config_is_fixed_to_selected_settings(self):
        task = validate_task({"title": "Inspect all workspaces"})
        self.assertEqual(task["workspace_scope"], "all")
        self.assertEqual(task["autonomy"], "supervised")
        self.assertEqual(task["feedback"], "both")
        self.assertEqual(task["mode"], "paper")
        self.assertFalse(task["live_trading_enabled"])

    def test_task_cannot_escalate_autonomy_or_disable_feedback(self):
        for task in (
            {"title": "unsafe", "autonomy": "full"},
            {"title": "unsafe", "feedback": "dashboard"},
        ):
            with self.assertRaises(ValueError):
                validate_task(task)

    def test_feedback_report_has_bounded_fields_and_https_evidence(self):
        event = feedback_event(task_id="t-1", agent="qa", status="completed",
                               evidence_urls=["https://github.com/example/pr/1"])
        self.assertEqual(event["deployment"], "not_attempted")
        self.assertEqual(event["mode"], "paper")
        self.assertFalse(event["live_trading_enabled"])
        with self.assertRaises(ValueError):
            feedback_event(task_id="t-1", agent="qa", status="completed",
                           evidence_urls=["http://insecure.example"])


if __name__ == "__main__":
    unittest.main()
