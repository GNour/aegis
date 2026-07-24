"""Cleanup runs only after every preservation receipt exists; else it refuses."""


def test_cleanup_refuses_missing_knowledge_receipt(cleanup, completed_task) -> None:
    completed_task.knowledge_sync.openviking_receipt = None
    result = cleanup.run(completed_task)
    assert result.state == "recovery_required"
    assert result.deleted == []


def test_cleanup_refuses_unresolved_decision(cleanup, completed_task) -> None:
    completed_task.unresolved_mandatory_decisions = 1
    result = cleanup.run(completed_task)
    assert result.state == "recovery_required"
    assert "no_unresolved_decisions" in result.missing_preconditions


def test_cleanup_refuses_missing_qmd_receipt(cleanup, completed_task) -> None:
    completed_task.knowledge_sync.qmd_receipt = None
    result = cleanup.run(completed_task)
    assert result.state == "recovery_required"
    assert "qmd_receipt" in result.missing_preconditions


def test_cleanup_refuses_unverified_writes(cleanup, completed_task) -> None:
    completed_task.verification_passed = False
    result = cleanup.run(completed_task)
    assert result.state == "recovery_required"


def test_cleanup_runs_exact_removal_when_all_receipts_present(
    cleanup, completed_task, service_runtime, removed_worktrees
) -> None:
    result = cleanup.run(completed_task)
    assert result.state == "cleaned"
    assert result.verified is True
    assert result.missing_preconditions == []
    # exact-label service and worktree removal happened and were verified absent
    assert service_runtime.exists(completed_task.identity) is False
    assert removed_worktrees == [completed_task.task_id]
    assert all("prune" not in cmd for cmd in service_runtime.commands)
    assert completed_task.identity.compose_project in result.deleted
