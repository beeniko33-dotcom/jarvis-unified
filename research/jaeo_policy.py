"""Jarvis Autonomous Engineering & Operations policy core.

This module is deliberately provider-agnostic and fail-closed. It does not call
external services, deploy infrastructure, or execute trading actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import Any


class Decision(StrEnum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    ENGINEERING = "engineering"
    DATABASE = "database"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    QA = "qa"
    RESEARCH = "research"
    RELEASE = "release"
    AUDIT = "audit"


class Action(StrEnum):
    INSPECT = "inspect"
    TEST = "test"
    CREATE_BRANCH = "create_branch"
    OPEN_PULL_REQUEST = "open_pull_request"
    CHANGE_CODE = "change_code"
    CHANGE_SCHEMA = "change_schema"
    CHANGE_SECRET = "change_secret"
    PROVISION_RESOURCE = "provision_resource"
    CREATE_CRON = "create_cron"
    DEPLOY_PREVIEW = "deploy_preview"
    DEPLOY_PRODUCTION = "deploy_production"
    MERGE_PULL_REQUEST = "merge_pull_request"
    CHANGE_OPERATOR_CONTROLS = "change_operator_controls"
    LIVE_TRADE = "live_trade"
    RESEARCH = "research"


PRODUCTION_RESOURCE_IDS = frozenset({
    "zythldptlplyutphgxpg",
    "db.zythldptlplyutphgxpg.supabase.co",
    "jarvis-control-worker",
    "production",
    "prod",
})
ALLOWED_AGENTS = frozenset(role.value for role in AgentRole)
SAFE_AUTONOMOUS_ACTIONS = frozenset({
    Action.INSPECT.value, Action.TEST.value, Action.CREATE_BRANCH.value,
    Action.OPEN_PULL_REQUEST.value, Action.RESEARCH.value,
})
ALWAYS_APPROVAL_ACTIONS = frozenset({
    Action.CHANGE_CODE.value, Action.CHANGE_SCHEMA.value,
    Action.CHANGE_SECRET.value, Action.PROVISION_RESOURCE.value,
    Action.CREATE_CRON.value, Action.DEPLOY_PREVIEW.value,
    Action.DEPLOY_PRODUCTION.value, Action.MERGE_PULL_REQUEST.value,
    Action.CHANGE_OPERATOR_CONTROLS.value,
})


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    requires_human_approval: bool
    mode: str = "supervised"
    live_trading_enabled: bool = False


def _approval_is_valid(
    approval: Any, *, action: str, resource_id: str, task_id: str | None,
    requester_id: str | None, request_hash: str | None, now: datetime | None,
) -> bool:
    """Validate a service-role-fetched approval bound to this task and request."""
    if not isinstance(approval, dict) or not task_id:
        return False
    required = (
        "id", "task_id", "status", "action", "resource_id", "requested_by",
        "decided_by_user_id", "request_hash", "decided_at", "expires_at",
    )
    if any(not approval.get(key) for key in required):
        return False
    if not requester_id or not request_hash or not re.fullmatch(r"[0-9a-f]{64}", request_hash):
        return False
    if approval["status"] != "approved" or approval["action"] != action:
        return False
    if approval["resource_id"] != resource_id or str(approval["task_id"]) != str(task_id):
        return False
    if str(approval["requested_by"]) != str(requester_id):
        return False
    if str(approval["decided_by_user_id"]) == str(requester_id):
        return False
    if approval["request_hash"] != request_hash:
        return False
    try:
        decided_at = datetime.fromisoformat(str(approval["decided_at"]).replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if decided_at.tzinfo is None or expires_at.tzinfo is None:
            return False
        if current.tzinfo is None or current.utcoffset() is None:
            return False
        return decided_at <= current < expires_at
    except (TypeError, ValueError, OverflowError):
        return False


def evaluate_action(
    *,
    agent: str,
    action: str,
    resource_id: str | None = None,
    environment: str | None = None,
    approval_record: dict[str, Any] | None = None,
    task_id: str | None = None,
    requester_id: str | None = None,
    request_hash: str | None = None,
    now: datetime | None = None,
) -> PolicyResult:
    """Evaluate a requested operation. Unknown roles/actions fail closed."""
    if agent not in ALLOWED_AGENTS:
        return PolicyResult(Decision.DENY, "unknown agent role", False)
    if action not in {item.value for item in Action}:
        return PolicyResult(Decision.DENY, "unknown action", False)

    resource = (resource_id or "").strip().lower()
    env = (environment or "").strip().lower()
    if action == Action.LIVE_TRADE.value:
        return PolicyResult(Decision.DENY, "live trading is permanently disabled", False)
    if action == Action.CHANGE_OPERATOR_CONTROLS.value:
        return PolicyResult(Decision.DENY, "operator controls are immutable to JAEO", False)
    if action == Action.DEPLOY_PRODUCTION.value:
        return PolicyResult(Decision.DENY, "production deployment is outside JAEO authority", False)
    is_production = resource in PRODUCTION_RESOURCE_IDS or env in PRODUCTION_RESOURCE_IDS
    if is_production and action != Action.INSPECT.value:
        return PolicyResult(Decision.DENY, "production resources are read-only to JAEO", False)
    if action in ALWAYS_APPROVAL_ACTIONS:
        if _approval_is_valid(
            approval_record, action=action, resource_id=resource_id or "",
            task_id=task_id, requester_id=requester_id,
            request_hash=request_hash, now=now,
        ):
            return PolicyResult(Decision.ALLOW, "task-bound, unexpired persisted approval verified", False)
        return PolicyResult(
            Decision.APPROVAL_REQUIRED,
            "a task-bound, unexpired persisted human approval is required",
            True,
        )
    if action in SAFE_AUTONOMOUS_ACTIONS:
        return PolicyResult(Decision.ALLOW, "permitted low-risk supervised operation", False)
    return PolicyResult(Decision.DENY, "action is not permitted by policy", False)


def validate_task(task: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a task request without executing it."""
    if not isinstance(task, dict):
        raise ValueError("task must be an object")
    title = task.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("task title must contain 1-200 characters")
    agent = task.get("agent", AgentRole.ORCHESTRATOR.value)
    if agent not in ALLOWED_AGENTS:
        raise ValueError("unknown agent role")
    scope = task.get("workspace_scope", "all")
    if scope not in {"all", "core"}:
        raise ValueError("workspace_scope must be all or core")
    autonomy = task.get("autonomy", "supervised")
    if autonomy != "supervised":
        raise ValueError("JAEO is configured for supervised autonomy only")
    feedback = task.get("feedback", "both")
    if feedback != "both":
        raise ValueError("JAEO feedback is configured for dashboard and reports")
    return {
        "title": title.strip(),
        "description": str(task.get("description", ""))[:4000],
        "agent": agent,
        "workspace_scope": scope,
        "autonomy": autonomy,
        "feedback": feedback,
        "mode": "supervised",
        "live_trading_enabled": False,
    }


def feedback_event(
    *,
    task_id: str,
    agent: str,
    status: str,
    inspected: list[str] | None = None,
    changed: list[str] | None = None,
    tests: list[dict[str, Any]] | None = None,
    deployment: str = "not_attempted",
    errors: list[str] | None = None,
    evidence_urls: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    """Create a bounded, credential-free progress report payload."""
    if agent not in ALLOWED_AGENTS:
        raise ValueError("unknown agent role")
    if status not in {"queued", "running", "awaiting_approval", "completed", "failed", "blocked"}:
        raise ValueError("invalid task status")
    urls = evidence_urls or []
    if any(not isinstance(url, str) or not url.startswith("https://") for url in urls):
        raise ValueError("evidence URLs must use https")
    return {
        "task_id": task_id, "agent": agent, "status": status,
        "inspected": (inspected or [])[:50], "changed": (changed or [])[:50],
        "tests": (tests or [])[:50], "deployment": deployment,
        "errors": (errors or [])[:20], "evidence_urls": urls[:50],
        "recommendations": (recommendations or [])[:20],
        "mode": "supervised", "live_trading_enabled": False,
    }
