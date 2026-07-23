"""Task lifecycle state and its legal transitions."""

from enum import StrEnum
from typing import Final


class TaskState(StrEnum):
    """The persisted lifecycle states for a task."""

    INTAKE = "intake"
    CLARIFY = "clarify"
    PLANNED = "planned"
    READY = "ready"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    PRESERVING = "preserving"
    CLEANING = "cleaning"
    WAITING_HUMAN = "waiting_human"
    WAITING_QUOTA = "waiting_quota"
    WAITING_PROVIDER = "waiting_provider"
    RETRY_SCHEDULED = "retry_scheduled"
    BLOCKED = "blocked"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: Final[dict[TaskState, frozenset[TaskState]]] = {
    TaskState.INTAKE: frozenset({TaskState.CLARIFY, TaskState.CANCELLED}),
    TaskState.CLARIFY: frozenset(
        {TaskState.PLANNED, TaskState.WAITING_HUMAN, TaskState.CANCELLED}
    ),
    TaskState.PLANNED: frozenset({TaskState.READY, TaskState.WAITING_HUMAN, TaskState.CANCELLED}),
    TaskState.READY: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.VERIFYING,
            TaskState.WAITING_HUMAN,
            TaskState.WAITING_QUOTA,
            TaskState.WAITING_PROVIDER,
            TaskState.RETRY_SCHEDULED,
            TaskState.BLOCKED,
            TaskState.RECOVERY_REQUIRED,
            TaskState.CANCELLED,
            TaskState.FAILED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {TaskState.REVIEWING, TaskState.EXECUTING, TaskState.RECOVERY_REQUIRED, TaskState.FAILED}
    ),
    TaskState.REVIEWING: frozenset(
        {TaskState.PRESERVING, TaskState.EXECUTING, TaskState.WAITING_HUMAN, TaskState.FAILED}
    ),
    TaskState.PRESERVING: frozenset({TaskState.CLEANING, TaskState.RECOVERY_REQUIRED}),
    TaskState.CLEANING: frozenset({TaskState.COMPLETE, TaskState.RECOVERY_REQUIRED}),
    TaskState.WAITING_HUMAN: frozenset(
        {
            TaskState.CLARIFY,
            TaskState.READY,
            TaskState.EXECUTING,
            TaskState.REVIEWING,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_QUOTA: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.WAITING_PROVIDER: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.RETRY_SCHEDULED: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.BLOCKED: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.RECOVERY_REQUIRED: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.PRESERVING,
            TaskState.CLEANING,
            TaskState.CANCELLED,
            TaskState.FAILED,
        }
    ),
    TaskState.COMPLETE: frozenset(),
    TaskState.CANCELLED: frozenset(),
    TaskState.FAILED: frozenset(),
}


def assert_transition(current: TaskState, target: TaskState) -> None:
    """Raise when a task lifecycle transition is not allowlisted."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"illegal task transition: {current.value} -> {target.value}")
