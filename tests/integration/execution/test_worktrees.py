"""Worktree create/remove against a real temporary Git repository."""

import subprocess
from pathlib import Path

import pytest

from aegis.execution.command import CommandError
from aegis.execution.worktrees import WorktreeManager

TASK_ID = "018f8bd9-19d6-7902-9018-593c0a97ea8a"


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "-C", str(path), "init", "-q", "-b", "main"], check=True, env=env)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, env=env)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True, env={**env}
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    _init_repo(repo)
    return repo


def test_create_and_remove_worktree(repo: Path, tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / "worktrees")
    path, branch = manager.create(repo, "main", TASK_ID, "Fix Login")
    assert path.exists()
    assert (path / "README.md").exists()
    assert branch == "task/018f8bd9-fix-login"
    assert path.is_relative_to((tmp_path / "worktrees").resolve())

    manager.remove(repo, TASK_ID)
    assert not path.exists()


def test_create_rejects_traversal_task_id(repo: Path, tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / "worktrees")
    with pytest.raises(ValueError, match="invalid task id"):
        manager.create(repo, "main", "../../escape", "slug")


def test_symlinked_root_still_contains_path(repo: Path, tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "link"
    link_root.symlink_to(real_root)
    manager = WorktreeManager(link_root)
    path = manager.path_for(TASK_ID)
    assert path.is_relative_to(real_root.resolve())


def test_remove_missing_worktree_raises(repo: Path, tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / "worktrees")
    with pytest.raises(CommandError):
        manager.remove(repo, TASK_ID)
