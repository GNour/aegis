"""Any preservation failure keeps cleanup locked and stays recoverable."""

import pytest

from aegis.domain.ids import new_uuid7
from aegis.domain.models import KnowledgeSync
from aegis.knowledge.preserve import Evidence, PreservationCoordinator


class FakeRenderer:
    def render(self, evidence: Evidence) -> str:
        return f"# {evidence.task_id}\n"


class FakeGit:
    def __init__(self) -> None:
        self.commits: list[str] = []
        self.source_uri = "git://brain/project-a.md"

    def commit(self, markdown: str, message: str) -> str:
        self.commits.append(message)
        return f"commit-{len(self.commits)}"


class FakeQmd:
    def __init__(self) -> None:
        self.fail_next = False

    def update_and_verify(self, project_id: str, commit: str) -> str:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("qmd failed")
        return f"qmd-{commit}"


class FakeOpenViking:
    def __init__(self) -> None:
        self.fail_next = False

    def ingest_commit(self, project_id: str, source_uri: str, commit: str, markdown: str) -> str:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("openviking failed")
        return f"ov-{commit}"


class FakeStore:
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
def coordinator(git, qmd, openviking) -> PreservationCoordinator:
    return PreservationCoordinator(
        renderer=FakeRenderer(), git=git, qmd=qmd, openviking=openviking, store=FakeStore()
    )


@pytest.fixture
def completed_evidence() -> Evidence:
    return Evidence(task_id=new_uuid7(), project_id="project-a", content="facts")


def test_openviking_failure_keeps_cleanup_locked(coordinator, completed_evidence, openviking) -> None:
    openviking.fail_next = True
    sync = coordinator.preserve(completed_evidence)
    assert sync.ready_for_cleanup is False
    assert sync.state == "recovery_required"
    assert sync.openviking_receipt is None
    # the canonical commit and the qmd receipt survive for resume
    assert sync.canonical_commit == "commit-1"
    assert sync.qmd_receipt is not None


def test_qmd_failure_keeps_cleanup_locked(coordinator, completed_evidence, qmd) -> None:
    qmd.fail_next = True
    sync = coordinator.preserve(completed_evidence)
    assert sync.ready_for_cleanup is False
    assert sync.state == "recovery_required"
    assert sync.qmd_receipt is None


def test_resume_reuses_commit_and_retries_only_missing_receipts(
    coordinator, completed_evidence, openviking, git
) -> None:
    openviking.fail_next = True
    first = coordinator.preserve(completed_evidence)
    assert first.ready_for_cleanup is False

    # resume with the same canonical commit; openviking now succeeds
    second = coordinator.preserve(completed_evidence, canonical_commit=first.canonical_commit)
    assert second.ready_for_cleanup is True
    assert second.canonical_commit == first.canonical_commit
    assert second.openviking_source_commit == first.canonical_commit
    # the git commit was not rewritten on resume
    assert len(git.commits) == 1
