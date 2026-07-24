"""A fake control client and app fixtures for TUI tests."""

from dataclasses import dataclass, field

import pytest

from aegis.client import AegisClientError
from aegis.policy.approvals import digest as action_digest_of
from aegis.tui.app import AegisTui


@dataclass
class CreatedTask:
    project_id: str
    request: str
    flow_id: str


@dataclass
class ApprovalCall:
    approval_id: str
    action_digest: str


@dataclass
class RejectCall:
    approval_id: str
    reason: str


@dataclass
class PendingApproval:
    id: str
    action_payload: dict
    scope: str
    risk: str
    expires_at: str
    effect: str
    kind: str = "approval"
    action_digest: str = field(default="")

    def __post_init__(self) -> None:
        if not self.action_digest:
            self.action_digest = action_digest_of(self.action_payload)


class FakeClient:
    def __init__(self) -> None:
        self.created: list[CreatedTask] = []
        self.approved: list[dict] = []
        self.rejected: list[dict] = []
        self.resumed: list[dict] = []
        self.cancelled: list[dict] = []
        self._counter = 0
        self.fail_get = False

    def list_flows(self) -> dict:
        return {"flows": [{"flow_id": "auto", "version": 1}, {"flow_id": "feature", "version": 2}]}

    def create_task(
        self,
        *,
        project_id: str,
        request: str,
        flow_id: str = "auto",
        risk: str = "low",
        acceptance_criteria: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> dict:
        self.created.append(CreatedTask(project_id, request, flow_id))
        self._counter += 1
        return {"task_id": f"task-{self._counter:03d}", "routing_reason": "matched auto rule"}

    def get_task(self, task_id: str) -> dict:
        if self.fail_get:
            raise AegisClientError("not_found", "unknown task", "r1")
        return {
            "task_id": task_id,
            "state": "planning",
            "version": 1,
            "waits": [],
            "decisions": [],
            "sessions": [],
            "artifacts": [],
        }

    def approve_action(self, approval_id: str, *, action_payload, comment=None, idempotency_key):
        self.approved.append(ApprovalCall(approval_id, action_digest_of(action_payload)))
        return {"approval_id": approval_id, "used": True}

    def reject_action(self, approval_id: str, *, reason: str, idempotency_key):
        self.rejected.append(RejectCall(approval_id, reason))
        return {"approval_id": approval_id, "used": True}

    def resume_task(self, task_id, *, expected_state, expected_version, reason, idempotency_key):
        self.resumed.append({"task_id": task_id})
        return {"task_id": task_id, "state": "planning"}

    def cancel_task(self, task_id, *, reason, cleanup_mode="graceful", idempotency_key):
        self.cancelled.append({"task_id": task_id, "reason": reason})
        return {"task_id": task_id, "state": "cancelled"}


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def tui_app(fake_client: FakeClient) -> AegisTui:
    return AegisTui(fake_client)


@pytest.fixture
def pending_approval() -> PendingApproval:
    return PendingApproval(
        id="ap-1",
        action_payload={"action": "task.cancel", "task_id": "t1"},
        scope="task.cancel",
        risk="high",
        expires_at="2026-07-24T13:00:00Z",
        effect="cancels task t1 and cleans its resources",
    )
