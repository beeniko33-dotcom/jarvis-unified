"""Typed, fail-closed JAEO command classification.

This module classifies user requests into bounded tasks. It does not execute
commands, call tools, access credentials, submit applications, deploy, or trade.
Unrecognized natural language is queued for clarification rather than guessed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import re


class CommandRisk(StrEnum):
    LOW = "low"
    REVIEW = "human_review"
    BLOCKED = "blocked"


class CommandAction(StrEnum):
    INSPECT = "inspect"
    RESEARCH = "paper_research"
    TEST = "test"
    PREPARE_PR = "open_pull_request"
    DRAFT_APPLICATION = "draft_application"
    SUBMIT_APPLICATION = "submit_application"
    TRADE = "trade"
    DEPLOY = "deploy"
    CHANGE_CONTROLS = "change_operator_controls"
    MANAGE_CREDENTIALS = "manage_credentials"
    MONEY_MOVEMENT = "money_movement"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CommandIntent:
    action: CommandAction
    risk: CommandRisk
    task_title: str
    requires_human_approval: bool
    executable_by_jaeo: bool
    reason: str


# Any sensitive verb anywhere in a compound request takes precedence over
# otherwise-safe leading words such as "research" or "inspect".
_SENSITIVE_ANYWHERE = re.compile(
    r"\\b(trade|trading order|place order|buy|sell|deploy|merge|"
    r"disable kill switch|pause entries|resume entries|change operator controls|"
    r"submit application|apply for job|withdraw|deposit|transfer|pay|"
    r"api key|token|password|secret)\\b",
    re.I,
)

# Explicit phrases only. Do not infer a sensitive action from ambiguous text.
_COMMANDS: tuple[tuple[re.Pattern[str], CommandAction, CommandRisk, str], ...] = (
    (re.compile(r"^(inspect|check status|audit status)$", re.I),
     CommandAction.INSPECT, CommandRisk.LOW, "read-only inspection"),
    (re.compile(r"^(research|analyze|analyse)\b", re.I),
     CommandAction.RESEARCH, CommandRisk.LOW, "research produces observations, not orders"),
    (re.compile(r"^(run tests|test)\b", re.I),
     CommandAction.TEST, CommandRisk.LOW, "tests are non-production operations"),
    (re.compile(r"^(prepare pull request|open pull request|prepare pr)$", re.I),
     CommandAction.PREPARE_PR, CommandRisk.REVIEW, "branch/PR changes require scoped review"),
    (re.compile(r"^(draft application|prepare application)\b", re.I),
     CommandAction.DRAFT_APPLICATION, CommandRisk.LOW, "draft only; no external submission"),
    (re.compile(r"^(submit application|apply for job)\b", re.I),
     CommandAction.SUBMIT_APPLICATION, CommandRisk.REVIEW, "external submission requires per-item approval"),
    (re.compile(r"^(trade|place order|buy|sell)\b", re.I),
     CommandAction.TRADE, CommandRisk.BLOCKED, "trading is not authorized by JAEO command routing"),
    (re.compile(r"^(deploy|publish to production)\b", re.I),
     CommandAction.DEPLOY, CommandRisk.BLOCKED, "production deployment is outside JAEO authority"),
    (re.compile(r"^(disable kill switch|pause entries|resume entries|change operator controls)$", re.I),
     CommandAction.CHANGE_CONTROLS, CommandRisk.BLOCKED, "operator controls cannot be changed by JAEO"),
    (re.compile(r"^(reveal|rotate|set|change) (api )?(key|token|password|secret)\b", re.I),
     CommandAction.MANAGE_CREDENTIALS, CommandRisk.BLOCKED, "credential actions require a separate secure workflow"),
    (re.compile(r"^(pay|withdraw|deposit|transfer|purchase)\b", re.I),
     CommandAction.MONEY_MOVEMENT, CommandRisk.BLOCKED, "money movement is outside JAEO authority"),
)


def classify_command(command: str) -> CommandIntent:
    """Classify a command without interpreting arbitrary instructions."""
    if not isinstance(command, str) or not command.strip() or len(command) > 500:
        raise ValueError("command must contain 1-500 characters")
    normalized = " ".join(command.strip().split())
    sensitive = _SENSITIVE_ANYWHERE.search(normalized)
    if sensitive:
        return CommandIntent(
            action=CommandAction.UNKNOWN,
            risk=CommandRisk.BLOCKED,
            task_title=normalized[:200],
            requires_human_approval=True,
            executable_by_jaeo=False,
            reason="compound or embedded sensitive instruction requires separate review",
        )
    for pattern, action, risk, reason in _COMMANDS:
        if pattern.search(normalized):
            return CommandIntent(
                action=action,
                risk=risk,
                task_title=normalized[:200],
                requires_human_approval=risk == CommandRisk.REVIEW,
                executable_by_jaeo=risk == CommandRisk.LOW,
                reason=reason,
            )
    return CommandIntent(
        action=CommandAction.UNKNOWN,
        risk=CommandRisk.REVIEW,
        task_title=normalized[:200],
        requires_human_approval=True,
        executable_by_jaeo=False,
        reason="unrecognized request; clarify intent and required scope",
    )


def build_task_envelope(*, command: str, actor_id: str, request_id: str) -> dict[str, object]:
    """Create an idempotent, paper-mode task envelope; never executes it."""
    if not isinstance(actor_id, str) or not actor_id.strip() or len(actor_id) > 128:
        raise ValueError("actor_id must contain 1-128 characters")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
        raise ValueError("request_id must contain 1-128 characters")
    intent = classify_command(command)
    digest = hashlib.sha256(
        f"{actor_id.strip()}:{request_id.strip()}:{command.strip()}".encode("utf-8")
    ).hexdigest()
    return {
        "task_idempotency_key": digest,
        "actor_id": actor_id.strip(),
        "request_id": request_id.strip(),
        "intent": asdict(intent),
        "status": "awaiting_approval" if intent.requires_human_approval else "queued",
        "mode": "paper",
        "live_trading_enabled": False,
        "execution_started": False,
    }
