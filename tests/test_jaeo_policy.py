from __future__ import annotations

import pytest

from research.jaeo_policy import (
    Action, Decision, evaluate_action, feedback_event, validate_task,
)


def test_safe_inspection_and_test_are_allowed():
    for action in (Action.INSPECT.value, Action.TEST.value, Action.CREATE_BRANCH.value):
        result = evaluate_action(agent="engineering", action=action, resource_id="jarvis-preview")
        assert result.decision is Decision.ALLOW
        assert result.mode == "paper"
        assert result.live_trading_enabled is False


def test_mutations_require_human_approval():
    for action in (
        Action.CHANGE_CODE.value, Action.CHANGE_SCHEMA.value,
        Action.PROVISION_RESOURCE.value, Action.CREATE_CRON.value,
        Action.DEPLOY_PREVIEW.value, Action.MERGE_PULL_REQUEST.value,
    ):
        result = evaluate_action(agent="engineering", action=action, resource_id="preview")
        assert result.decision is Decision.APPROVAL_REQUIRED
        assert result.requires_human_approval


def test_explicit_approval_only_authorizes_approvable_action():
    result = evaluate_action(agent="database", action=Action.CHANGE_SCHEMA.value,
                             resource_id="isolated-prototype", approval_granted=True)
    assert result.decision is Decision.ALLOW


@pytest.mark.parametrize("action", [
    Action.LIVE_TRADE.value, Action.DEPLOY_PRODUCTION.value,
    Action.CHANGE_OPERATOR_CONTROLS.value,
])
def test_critical_actions_are_never_authorized(action):
    result = evaluate_action(agent="release", action=action, approval_granted=True)
    assert result.decision is Decision.DENY


@pytest.mark.parametrize("resource", [
    "zythldptlplyutphgxpg", "db.zythldptlplyutphgxpg.supabase.co",
    "jarvis-control-worker", "production",
])
def test_production_resources_are_denied(resource):
    result = evaluate_action(agent="infrastructure", action=Action.INSPECT.value,
                             resource_id=resource)
    assert result.decision is Decision.DENY


def test_unknown_agent_and_action_fail_closed():
    assert evaluate_action(agent="root", action="inspect").decision is Decision.DENY
    assert evaluate_action(agent="audit", action="shell").decision is Decision.DENY


def test_task_config_is_fixed_to_selected_settings():
    task = validate_task({"title": "Inspect all workspaces"})
    assert task["workspace_scope"] == "all"
    assert task["autonomy"] == "supervised"
    assert task["feedback"] == "both"
    assert task["mode"] == "paper"
    assert task["live_trading_enabled"] is False


def test_task_cannot_escalate_autonomy_or_disable_feedback():
    with pytest.raises(ValueError):
        validate_task({"title": "unsafe", "autonomy": "full"})
    with pytest.raises(ValueError):
        validate_task({"title": "unsafe", "feedback": "dashboard"})


def test_feedback_report_has_bounded_fields_and_https_evidence():
    event = feedback_event(task_id="t-1", agent="qa", status="completed",
                           evidence_urls=["https://github.com/example/pr/1"])
    assert event["deployment"] == "not_attempted"
    assert event["mode"] == "paper"
    assert event["live_trading_enabled"] is False
    with pytest.raises(ValueError):
        feedback_event(task_id="t-1", agent="qa", status="completed",
                       evidence_urls=["http://insecure.example"])
