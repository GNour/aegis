import pytest

from aegis.domain.state import TaskState, assert_transition


def test_normal_and_wait_transitions_are_legal() -> None:
    assert_transition(TaskState.INTAKE, TaskState.CLARIFY)
    assert_transition(TaskState.EXECUTING, TaskState.WAITING_QUOTA)
    assert_transition(TaskState.WAITING_QUOTA, TaskState.EXECUTING)


def test_complete_cannot_return_to_execution() -> None:
    with pytest.raises(ValueError, match="illegal task transition"):
        assert_transition(TaskState.COMPLETE, TaskState.EXECUTING)


def test_every_allowlisted_edge_is_legal_and_each_state_has_an_illegal_target() -> None:
    allowed = {
        TaskState.INTAKE: {TaskState.CLARIFY, TaskState.CANCELLED},
        TaskState.CLARIFY: {TaskState.PLANNED, TaskState.WAITING_HUMAN, TaskState.CANCELLED},
        TaskState.PLANNED: {TaskState.READY, TaskState.WAITING_HUMAN, TaskState.CANCELLED},
        TaskState.READY: {TaskState.EXECUTING, TaskState.CANCELLED},
        TaskState.EXECUTING: {
            TaskState.VERIFYING, TaskState.WAITING_HUMAN, TaskState.WAITING_QUOTA,
            TaskState.WAITING_PROVIDER, TaskState.RETRY_SCHEDULED, TaskState.BLOCKED,
            TaskState.RECOVERY_REQUIRED, TaskState.CANCELLED, TaskState.FAILED,
        },
        TaskState.VERIFYING: {TaskState.REVIEWING, TaskState.EXECUTING, TaskState.RECOVERY_REQUIRED, TaskState.FAILED},
        TaskState.REVIEWING: {TaskState.PRESERVING, TaskState.EXECUTING, TaskState.WAITING_HUMAN, TaskState.FAILED},
        TaskState.PRESERVING: {TaskState.CLEANING, TaskState.RECOVERY_REQUIRED},
        TaskState.CLEANING: {TaskState.COMPLETE, TaskState.RECOVERY_REQUIRED},
        TaskState.WAITING_HUMAN: {TaskState.CLARIFY, TaskState.READY, TaskState.EXECUTING, TaskState.REVIEWING, TaskState.CANCELLED},
        TaskState.WAITING_QUOTA: {TaskState.EXECUTING, TaskState.CANCELLED},
        TaskState.WAITING_PROVIDER: {TaskState.EXECUTING, TaskState.CANCELLED},
        TaskState.RETRY_SCHEDULED: {TaskState.EXECUTING, TaskState.CANCELLED},
        TaskState.BLOCKED: {TaskState.EXECUTING, TaskState.CANCELLED},
        TaskState.RECOVERY_REQUIRED: {TaskState.EXECUTING, TaskState.PRESERVING, TaskState.CLEANING, TaskState.CANCELLED, TaskState.FAILED},
        TaskState.COMPLETE: set(),
        TaskState.CANCELLED: set(),
        TaskState.FAILED: set(),
    }
    for current, targets in allowed.items():
        for target in targets:
            assert_transition(current, target)
        illegal_target = next(state for state in TaskState if state not in targets)
        with pytest.raises(ValueError, match="illegal task transition"):
            assert_transition(current, illegal_target)
