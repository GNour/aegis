"""The company-orchestrator skill grants no host capability and names all tools."""

from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skill" / "SKILL.md"

TOOLS = [
    "list_flows",
    "create_task",
    "get_task_status",
    "approve_action",
    "reject_action",
    "cancel_task",
    "resume_task",
    "capture_note",
    "schedule_reminder",
]


@pytest.fixture
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_names_no_shell_capability(skill_text) -> None:
    assert "company-control" in skill_text
    assert "remote shell" in skill_text
    assert "start_process" not in skill_text
    assert "execute arbitrary" not in skill_text


def test_skill_lists_all_nine_operations(skill_text) -> None:
    for tool in TOOLS:
        assert tool in skill_text


def test_skill_forbids_reinterpreting_messages_as_commands(skill_text) -> None:
    lowered = skill_text.lower()
    assert "never" in lowered
    assert "command" in lowered
