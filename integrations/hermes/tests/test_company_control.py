"""The Hermes company-control plugin exposes only typed, allowlisted tools."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))

from company_control import EXPECTED_TOOLS, CompanyControlPlugin  # noqa: E402


class ScopedFake:
    def __init__(self, actor: str, interface: str, sink: dict) -> None:
        self.actor = actor
        self.interface = interface
        self.sink = sink

    def create_task(self, *, project_id, request, flow_id="auto", idempotency_key, **kw):
        self.sink["create"] = {"actor": self.actor, "project_id": project_id, "request": request}
        return {"task_id": "task-001"}

    def list_flows(self):
        self.sink["list"] = {"actor": self.actor}
        return {"flows": []}

    def get_task(self, task_id):
        return {"task_id": task_id, "state": "planning"}

    def approve_action(self, approval_id, *, action_payload, idempotency_key, **kw):
        self.sink["approve"] = {"actor": self.actor, "approval_id": approval_id}
        return {"approval_id": approval_id, "used": True}

    def reject_action(self, approval_id, *, reason, idempotency_key):
        return {"approval_id": approval_id, "used": True}

    def cancel_task(self, task_id, *, reason, idempotency_key, **kw):
        return {"task_id": task_id}

    def resume_task(self, task_id, *, expected_state, expected_version, reason, idempotency_key):
        return {"task_id": task_id}

    def create_note(self, *, markdown_text, idempotency_key, **kw):
        return {"note_id": "n1"}

    def create_reminder(self, *, message, schedule, timezone, idempotency_key):
        return {"reminder_id": "r1"}


class FakeControlClient:
    def __init__(self) -> None:
        self.sink: dict = {}

    def for_actor(self, actor: str, interface: str) -> ScopedFake:
        return ScopedFake(actor, interface, self.sink)


@pytest.fixture
def plugin() -> CompanyControlPlugin:
    return CompanyControlPlugin(FakeControlClient(), allowed_users={42: "owner-actor-id"})


def test_plugin_exposes_only_typed_tools(plugin) -> None:
    assert set(plugin.tools) == EXPECTED_TOOLS


def test_unknown_telegram_user_is_rejected(plugin) -> None:
    with pytest.raises(PermissionError, match="telegram user not allowed"):
        plugin.create_task(
            context={"telegram_user_id": 999}, project_id="demo", request="x", flow_id="auto"
        )


def test_allowed_user_is_mapped_to_actor(plugin) -> None:
    plugin.create_task(context={"telegram_user_id": 42}, project_id="demo", request="fix")
    assert plugin.client.sink["create"]["actor"] == "owner-actor-id"
    assert plugin.client.sink["create"]["project_id"] == "demo"


def test_request_length_is_bounded(plugin) -> None:
    with pytest.raises(ValueError, match="too long"):
        plugin.create_task(
            context={"telegram_user_id": 42}, project_id="demo", request="x" * 100000
        )


def test_control_characters_are_rejected(plugin) -> None:
    with pytest.raises(ValueError, match="control"):
        plugin.create_task(
            context={"telegram_user_id": 42}, project_id="demo", request="bad\x00request"
        )


def test_no_tool_accepts_a_command_field(plugin) -> None:
    import inspect

    for name in EXPECTED_TOOLS:
        params = set(inspect.signature(getattr(plugin, name)).parameters)
        assert "command" not in params
        assert "argv" not in params
        assert "args" not in params
