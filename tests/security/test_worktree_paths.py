"""Worktree paths stay contained under the managed root; branches are derived safely."""

import pytest

from aegis.execution.worktrees import WorktreeManager


def test_task_path_stays_under_root(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    with pytest.raises(ValueError, match="invalid task id"):
        manager.path_for("../../escape")


def test_non_uuid_task_id_is_rejected(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    with pytest.raises(ValueError, match="invalid task id"):
        manager.path_for("not-a-uuid")


def test_valid_task_path_is_under_root(tmp_path) -> None:
    root = tmp_path / "root"
    manager = WorktreeManager(root)
    task_id = "018f8bd9-19d6-7902-9018-593c0a97ea8a"
    path = manager.path_for(task_id)
    assert path.is_relative_to(root.resolve())
    assert path.name == task_id


def test_branch_is_derived_from_task_id(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    assert (
        manager.branch_for("018f8bd9-19d6-7902-9018-593c0a97ea8a", "Fix Login")
        == "task/018f8bd9-fix-login"
    )


def test_branch_slug_is_bounded_and_sanitized(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    branch = manager.branch_for(
        "018f8bd9-19d6-7902-9018-593c0a97ea8a", "  Weird///Chars!!! " + "x" * 80
    )
    slug = branch.removeprefix("task/018f8bd9-")
    assert len(slug) <= 40
    assert branch.startswith("task/018f8bd9-")
    assert "/" not in slug and "!" not in slug and " " not in slug
