"""Deterministic fakes for the preservation coordinator."""

import pytest

from aegis.domain.ids import new_uuid7
from aegis.domain.models import KnowledgeSync
from aegis.knowledge.preserve import Evidence, PreservationCoordinator


class FakeRenderer:
    def render(self, evidence: Evidence) -> str:
        return f"# {evidence.task_id}\n{evidence.content}\n"


class FakeGit:
    def __init__(self) -> None:
        self.commits: list[tuple[str, str]] = []
        self.source_uri = "git://brain/project-a.md"

    def commit(self, markdown: str, message: str) -> str:
        self.commits.append((markdown, message))
        return f"commit-{len(self.commits)}"


class FakeQmd:
    def __init__(self) -> None:
        self.fail_next = False
        self.calls: list[tuple[str, str]] = []

    def update_and_verify(self, project_id: str, commit: str) -> str:
        self.calls.append((project_id, commit))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("qmd indexing failed")
        return f"qmd-{commit}"


class FakeOpenViking:
    def __init__(self) -> None:
        self.fail_next = False
        self.calls: list[tuple[str, str, str]] = []

    def ingest_commit(self, project_id: str, source_uri: str, commit: str, markdown: str) -> str:
        self.calls.append((project_id, source_uri, commit))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("openviking ingest failed")
        return f"ov-{commit}"


class FakeKnowledgeStore:
    def __init__(self) -> None:
        self.saved: list[KnowledgeSync] = []

    def save_knowledge_sync(self, sync: KnowledgeSync) -> KnowledgeSync:
        self.saved.append(sync)
        return sync


@pytest.fixture
def git() -> FakeGit:
    return FakeGit()


@pytest.fixture
def qmd() -> FakeQmd:
    return FakeQmd()


@pytest.fixture
def openviking() -> FakeOpenViking:
    return FakeOpenViking()


@pytest.fixture
def store() -> FakeKnowledgeStore:
    return FakeKnowledgeStore()


@pytest.fixture
def coordinator(git, qmd, openviking, store) -> PreservationCoordinator:
    return PreservationCoordinator(
        renderer=FakeRenderer(), git=git, qmd=qmd, openviking=openviking, store=store
    )


@pytest.fixture
def completed_evidence() -> Evidence:
    return Evidence(task_id=new_uuid7(), project_id="project-a", content="preserved facts")
