"""Preservation-gated, exact-label cleanup.

Cleanup runs only after every preservation receipt exists (frozen writes, final
verification, review, valid handoff, artifact digests, canonical knowledge commit,
QMD and OpenViking receipts, and no unresolved mandatory decision). If any is
missing the task moves to ``recovery_required`` and nothing is deleted. When the
gate passes, cleanup removes only exact-label task services and the worktree, then
verifies their absence -- it never prunes or touches unlabeled resources.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from aegis.execution.resources import ResourceIdentity
from aegis.execution.services import ServiceRuntime


@dataclass
class KnowledgeReceipts:
    qmd_receipt: str | None
    openviking_receipt: str | None
    canonical_commit: str | None


@dataclass
class CompletedTask:
    task_id: str
    identity: ResourceIdentity
    knowledge_sync: KnowledgeReceipts
    writes_frozen: bool
    verification_passed: bool
    review_complete: bool
    handoff_valid: bool
    artifacts_have_digests: bool
    unresolved_mandatory_decisions: int


@dataclass(frozen=True)
class CleanupResult:
    state: str  # "cleaned" | "recovery_required"
    deleted: list[str] = field(default_factory=list)
    missing_preconditions: list[str] = field(default_factory=list)
    verified: bool = False


def _missing_preconditions(task: CompletedTask) -> list[str]:
    checks = {
        "writes_frozen": task.writes_frozen,
        "final_verification": task.verification_passed,
        "review_complete": task.review_complete,
        "handoff_valid": task.handoff_valid,
        "artifact_digests": task.artifacts_have_digests,
        "canonical_commit": bool(task.knowledge_sync.canonical_commit),
        "qmd_receipt": bool(task.knowledge_sync.qmd_receipt),
        "openviking_receipt": bool(task.knowledge_sync.openviking_receipt),
        "no_unresolved_decisions": task.unresolved_mandatory_decisions == 0,
    }
    return [name for name, ok in checks.items() if not ok]


class CleanupService:
    def __init__(
        self, *, service_runtime: ServiceRuntime, worktree_remover: Callable[[str], object]
    ) -> None:
        self._services = service_runtime
        self._remove_worktree = worktree_remover

    def run(self, task: CompletedTask) -> CleanupResult:
        missing = _missing_preconditions(task)
        if missing:
            return CleanupResult(state="recovery_required", missing_preconditions=missing)

        self._services.cleanup(task.identity)
        self._remove_worktree(task.task_id)

        verified = not self._exists(task.identity)
        if not verified:
            return CleanupResult(
                state="recovery_required",
                missing_preconditions=["resource_absence_unverified"],
            )
        return CleanupResult(
            state="cleaned",
            deleted=[task.identity.compose_project, f"worktree:{task.task_id}"],
            verified=True,
        )

    def _exists(self, identity: ResourceIdentity) -> bool:
        exists = getattr(self._services, "exists", None)
        return bool(exists(identity)) if callable(exists) else False
