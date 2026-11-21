from __future__ import annotations

import unittest
from datetime import datetime, timezone

from research.jaeo_policy import (
    Action, Decision, evaluate_action, feedback_event, validate_task,
)


NOW = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)


def approved(action, resource="isolated-prototype", task="task-1", **changes):
    value = {
        "id": "approval-123", "task_id": task, "status": "approved",
        "action": action, "resource_id": resource, "decided_by": "operator-1",
        "decided_at": "2026-11-20T20:00:00Z",
        "expires_at": "2026-11-20T22:00:00Z",
    }
    value.update(changes)
    return value


class JaeoPolicyTests(unittest.TestCase):
    def test_safe_inspection_and_test_are_allowed(self):
        for action in (Action.INSPECT.value, Action.TEST.value, Action.CREATE_BRANCH.value):
            result = evaluate_action(agent="engineering", action=action, resource_id="jarvis-preview")
            self.assertEqual(result.decision, Decision.ALLOW)
            self.assertEqual(result.mode, "supervised")
            self.assertFalse(result.live_trading_enabled)

    def test_mutations_require_human_approval(self):
        for action in (Action.CHANGE_SCHEMA.value, Action.PROVISION_RESOURCE.value,
                       Action.CREATE_CRON.value, Action.DEPLOY_PREVIEW.value,
                       Action.MERGE_PULL_REQUEST.value):
            result = evaluate_action(agent="engineering", action=action, resource_id="preview")
            self.assertEqual(result.decision, Decision.APPROVAL_REQUIRED)
            self.assertTrue(result.requires_human_approval)

    def test_explicit_approval_is_bound_to_task_action_and_resource(self):
        action = Action.CHANGE_SCHEMA.value
        result = evaluate_action(agent="database", action=action, resource_id="isolated-prototype",
                                 task_id="task-1", approval_record=approved(action), now=NOW)
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_approval_rejects_wrong_task_action_or_resource(self):
        action = Action.CHANGE_SCHEMA.value
        cases = [
            approved(action, task="another-task"),
            approved(Action.CHANGE_CODE.value),
            approved(action, resource="another-resource"),
            approved(action, expires_at="2026-11-20T20:59:00Z"),
            approved(action, decided_at="2026-11-20T21:01:00Z"),
            approved(action, expires_at=None),
            {"status": "approved", "action": action, "resource_id": "isolated-prototype",
             "decided_by": "operator", "decided_at": "2026-11-20T20:00:00Z"},
        ]
        for record in cases:
            with self.subTest(record=record):
                result = evaluate_action(agent="database", action=action,
                    resource_id="isolated-prototype", task_id="task-1",
                    approval_record=record, now=NOW)
                self.assertEqual(result.decision, Decision.APPROVAL_REQUIRED)

    def test_code_changes_need_task_bound_approval(self):
        action = Action.CHANGE_CODE.value
        result = evaluate_action(agent="engineering", action=action,
            resource_id="branch:feat/example", task_id="task-1",
            approval_record=approved(action, resource="branch:feat/example"), now=NOW)
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_production_workspace_is_read_only_even_with_approval(self):
        result = evaluate_action(agent="database", action=Action.CHANGE_SCHEMA.value,
            resource_id="zythldptlplyutphgxpg", task_id="task-1",
            approval_record=approved(Action.CHANGE_SCHEMA.value,
                resource="zythldptlplyutphgxpg"), now=NOW)
        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(evaluate_action(agent="audit", action=Action.INSPECT.value,
            resource_id="zythldptlplyutphgxpg").decision, Decision.ALLOW)

    def test_critical_actions_are_never_authorized(self):
        for action in (Action.LIVE_TRADE.value, Action.DEPLOY_PRODUCTION.value,
                       Action.CHANGE_OPERATOR_CONTROLS.value):
            result = evaluate_action(agent="release", action=action,
                approval_record=approved(action, resource=""), task_id="task-1", now=NOW)
            self.assertEqual(result.decision, Decision.DENY)

    def test_unknown_agent_and_action_fail_closed(self):
        self.assertEqual(evaluate_action(agent="root", action="inspect").decision, Decision.DENY)
        self.assertEqual(evaluate_action(agent="audit", action="shell").decision, Decision.DENY)

    def test_task_config_is_fixed_to_selected_settings(self):
        task = validate_task({"title": "Inspect all workspaces"})
        self.assertEqual(task["workspace_scope"], "all")
        self.assertEqual(task["autonomy"], "supervised")
        self.assertEqual(task["feedback"], "both")
        self.assertEqual(task["mode"], "supervised")
        self.assertFalse(task["live_trading_enabled"])

    def test_task_cannot_escalate_autonomy_or_disable_feedback(self):
        for task in ({"title": "unsafe", "autonomy": "full"},
                     {"title": "unsafe", "feedback": "dashboard"}):
            with self.assertRaises(ValueError):
                validate_task(task)

    def test_feedback_report_has_bounded_fields_and_https_evidence(self):
        event = feedback_event(task_id="t-1", agent="qa", status="completed",
                               evidence_urls=["https://github.com/example/pr/1"])
        self.assertEqual(event["deployment"], "not_attempted")
        self.assertEqual(event["mode"], "supervised")
        self.assertFalse(event["live_trading_enabled"])
        with self.assertRaises(ValueError):
            feedback_event(task_id="t-1", agent="qa", status="completed",
                           evidence_urls=["http://insecure.example"])


if __name__ == "__main__":
    unittest.main()
