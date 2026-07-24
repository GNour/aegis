"""Contained Git worktree management for isolated writing workers.

One worker writes in one Git worktree. Task ids must be UUIDs and the derived
worktree path is proven to stay under the managed root, so a crafted id can never
escape via traversal or an absolute component. Branches are derived deterministically
from the task id and a bounded, sanitized slug.
"""

import re
from pathlib import Path

from aegis.execution.command import CommandResult, run

_TASK_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


class WorktreeManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def path_for(self, task_id: str) -> Path:
        if _TASK_ID.fullmatch(task_id) is None:
            raise ValueError("invalid task id")
        path = (self.root / task_id).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("worktree path escapes root")
        return path

    def branch_for(self, task_id: str, slug: str) -> str:
        if _TASK_ID.fullmatch(task_id) is None:
            raise ValueError("invalid task id")
        safe = _SLUG_UNSAFE.sub("-", slug.lower()).strip("-")[:40].strip("-")
        return f"task/{task_id[:8]}-{safe}"

    def create(self, repo: Path, base: str, task_id: str, slug: str) -> tuple[Path, str]:
        path = self.path_for(task_id)
        branch = self.branch_for(task_id, slug)
        self.root.mkdir(parents=True, exist_ok=True)
        run(
            ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(path), base],
        )
        return path, branch

    def remove(self, repo: Path, task_id: str) -> CommandResult:
        path = self.path_for(task_id)
        return run(["git", "-C", str(repo), "worktree", "remove", str(path)])
