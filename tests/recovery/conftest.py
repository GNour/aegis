"""Fixtures for recovery classification, resume, and cleanup-gate tests."""

from datetime import UTC, datetime, timedelta

import pytest

from aegis.execution.cleanup import CleanupService, CompletedTask, KnowledgeReceipts
from aegis.execution.recovery import Failure, FailureClass, RecoveryEngine
from aegis.execution.resources import ResourceIdentity
from aegis.execution.services import FakeServiceRuntime

TASK_ID = "018f8bd9-19d6-7902-9018-593c0a97ea8a"


@pytest.fixture
def engine() -> RecoveryEngine:
    return RecoveryEngine()


@pytest.fixture
def credit_failure() -> Failure:
    return Failure(
        failure_class=FailureClass.CREDIT_LIMIT,
        provider="anthropic",
        model="opus",
        reset_at=datetime.now(UTC) + timedelta(hours=2),
    )


@pytest.fixture
def completed_task() -> CompletedTask:
    return CompletedTask(
        task_id=TASK_ID,
        identity=ResourceIdentity(instance="pilot", task_id=TASK_ID, nonce="n1"),
        knowledge_sync=KnowledgeReceipts(
            qmd_receipt="qmd-1", openviking_receipt="ov-1", canonical_commit="c0ffee"
        ),
        writes_frozen=True,
        verification_passed=True,
        review_complete=True,
        handoff_valid=True,
        artifacts_have_digests=True,
        unresolved_mandatory_decisions=0,
    )


@pytest.fixture
def service_runtime(completed_task: CompletedTask) -> FakeServiceRuntime:
    runtime = FakeServiceRuntime()
    runtime.seed(completed_task.identity)
    return runtime


@pytest.fixture
def removed_worktrees() -> list[str]:
    return []


@pytest.fixture
def cleanup(
    service_runtime: FakeServiceRuntime, removed_worktrees: list[str]
) -> CleanupService:
    return CleanupService(
        service_runtime=service_runtime, worktree_remover=removed_worktrees.append
    )
