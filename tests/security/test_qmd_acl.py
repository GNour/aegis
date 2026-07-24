"""QMD retrieval enforces collection/mode ACLs and bounded limits."""

import pytest

from aegis.execution.command import CommandResult
from aegis.knowledge.qmd import QmdAdapter, RetrievalScope


def _stub_runner(argv, **kwargs) -> CommandResult:
    return CommandResult(argv=tuple(argv), returncode=0, stdout="[]", stderr="")


@pytest.fixture
def qmd() -> QmdAdapter:
    return QmdAdapter(runner=_stub_runner)


@pytest.fixture
def task_scope() -> RetrievalScope:
    return RetrievalScope(
        task_id="t1", collections=frozenset({"project-a"}), modes=frozenset({"lexical"})
    )


def test_project_cannot_search_other_collection(qmd, task_scope) -> None:
    with pytest.raises(PermissionError, match="collection not allowed"):
        qmd.search(task_scope, collection="project-b", query="secrets", limit=5)


def test_qmd_limit_is_bounded(qmd, task_scope) -> None:
    with pytest.raises(ValueError, match="limit"):
        qmd.search(task_scope, collection="project-a", query="routes", limit=101)


def test_zero_limit_is_rejected(qmd, task_scope) -> None:
    with pytest.raises(ValueError, match="limit"):
        qmd.search(task_scope, collection="project-a", query="routes", limit=0)


def test_disallowed_mode_is_rejected(qmd, task_scope) -> None:
    with pytest.raises(PermissionError, match="mode"):
        qmd.search(task_scope, collection="project-a", query="routes", limit=5, mode="semantic")
