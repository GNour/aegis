"""Hermes ``company-control`` plugin.

Exposes exactly nine typed control tools to Hermes. Every call validates the Telegram
user against an allowlist, maps them to an Aegis actor, and dispatches through the
typed control client scoped to that actor over the ``telegram`` interface. Inputs are
length-bounded and reject control characters; no tool accepts a command or argument
array, so a chat message can never become host execution.
"""

import uuid
from typing import Any

EXPECTED_TOOLS = {
    "list_flows",
    "create_task",
    "get_task_status",
    "approve_action",
    "reject_action",
    "cancel_task",
    "resume_task",
    "capture_note",
    "schedule_reminder",
}

MAX_PROJECT = 200
MAX_REQUEST = 4000
MAX_REASON = 2000
MAX_NOTE = 8000
MAX_MESSAGE = 2000


def _idem() -> str:
    return str(uuid.uuid4())


def _bounded(text: str, limit: int, field: str) -> str:
    if not isinstance(text, str):
        raise ValueError(f"{field} must be text")
    if len(text) > limit:
        raise ValueError(f"{field} too long")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in text):
        raise ValueError(f"{field} contains control characters")
    return text


class CompanyControlPlugin:
    def __init__(self, client: Any, allowed_users: dict[int, str]) -> None:
        self.client = client
        self.allowed_users = allowed_users
        self.tools = {name: getattr(self, name) for name in EXPECTED_TOOLS}

    def actor(self, context: dict[str, object]) -> str:
        telegram_id = int(context["telegram_user_id"])  # type: ignore[arg-type]
        if telegram_id not in self.allowed_users:
            raise PermissionError("telegram user not allowed")
        return self.allowed_users[telegram_id]

    def _scoped(self, context: dict[str, object]) -> Any:
        return self.client.for_actor(self.actor(context), "telegram")

    # ── the nine typed tools ────────────────────────────────────────────────
    def list_flows(self, context: dict[str, object]) -> dict[str, Any]:
        return self._scoped(context).list_flows()

    def create_task(
        self,
        context: dict[str, object],
        project_id: str,
        request: str,
        flow_id: str = "auto",
    ) -> dict[str, Any]:
        _bounded(project_id, MAX_PROJECT, "project_id")
        _bounded(request, MAX_REQUEST, "request")
        _bounded(flow_id, MAX_PROJECT, "flow_id")
        return self._scoped(context).create_task(
            project_id=project_id, request=request, flow_id=flow_id, idempotency_key=_idem()
        )

    def get_task_status(self, context: dict[str, object], task_id: str) -> dict[str, Any]:
        return self._scoped(context).get_task(task_id)

    def approve_action(
        self, context: dict[str, object], approval_id: str, action_payload: dict[str, object]
    ) -> dict[str, Any]:
        return self._scoped(context).approve_action(
            approval_id, action_payload=action_payload, idempotency_key=_idem()
        )

    def reject_action(
        self, context: dict[str, object], approval_id: str, reason: str
    ) -> dict[str, Any]:
        _bounded(reason, MAX_REASON, "reason")
        return self._scoped(context).reject_action(
            approval_id, reason=reason, idempotency_key=_idem()
        )

    def cancel_task(
        self, context: dict[str, object], task_id: str, reason: str
    ) -> dict[str, Any]:
        _bounded(reason, MAX_REASON, "reason")
        return self._scoped(context).cancel_task(
            task_id, reason=reason, idempotency_key=_idem()
        )

    def resume_task(
        self,
        context: dict[str, object],
        task_id: str,
        expected_state: str,
        expected_version: int,
        reason: str,
    ) -> dict[str, Any]:
        _bounded(reason, MAX_REASON, "reason")
        return self._scoped(context).resume_task(
            task_id,
            expected_state=expected_state,
            expected_version=expected_version,
            reason=reason,
            idempotency_key=_idem(),
        )

    def capture_note(
        self,
        context: dict[str, object],
        markdown_text: str,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        _bounded(markdown_text, MAX_NOTE, "markdown_text")
        return self._scoped(context).create_note(
            markdown_text=markdown_text,
            project_id=project_id,
            task_id=task_id,
            idempotency_key=_idem(),
        )

    def schedule_reminder(
        self, context: dict[str, object], message: str, schedule: str, timezone: str
    ) -> dict[str, Any]:
        _bounded(message, MAX_MESSAGE, "message")
        return self._scoped(context).create_reminder(
            message=message, schedule=schedule, timezone=timezone, idempotency_key=_idem()
        )
