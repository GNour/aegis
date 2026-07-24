"""Knowledge preservation coordinator and cleanup lock.

Preservation commits canonical Markdown to Git first, then updates QMD and ingests
into OpenViking, recording receipts that both reference the exact canonical commit.
Only when both receipts exist is the task marked ready for cleanup. An adapter
failure produces a persisted partial sync with ``ready_for_cleanup=False`` and never
rolls back the Git commit or deletes resources; resume reuses the canonical commit
and retries only the missing receipts.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from aegis.domain.ids import new_uuid7
from aegis.domain.models import KnowledgeSync


@dataclass(frozen=True)
class Evidence:
    task_id: str
    project_id: str
    content: str = ""


class Renderer(Protocol):
    def render(self, evidence: Evidence) -> str: ...


class GitPort(Protocol):
    @property
    def source_uri(self) -> str: ...
    def commit(self, markdown: str, message: str) -> str: ...


class QmdPort(Protocol):
    def update_and_verify(self, project_id: str, commit: str) -> str: ...


class OpenVikingPort(Protocol):
    def ingest_commit(
        self, project_id: str, source_uri: str, commit: str, markdown: str
    ) -> str: ...


class KnowledgeStore(Protocol):
    def save_knowledge_sync(self, sync: KnowledgeSync) -> KnowledgeSync: ...


class PreservationCoordinator:
    def __init__(
        self,
        *,
        renderer: Renderer,
        git: GitPort,
        qmd: QmdPort,
        openviking: OpenVikingPort,
        store: KnowledgeStore,
    ) -> None:
        self.renderer = renderer
        self.git = git
        self.qmd = qmd
        self.openviking = openviking
        self.store = store

    def preserve(
        self, evidence: Evidence, *, canonical_commit: str | None = None
    ) -> KnowledgeSync:
        markdown = self.renderer.render(evidence)
        commit = canonical_commit or self.git.commit(
            markdown, message=f"docs(task): preserve {evidence.task_id}"
        )

        qmd_receipt = self._try(lambda: self.qmd.update_and_verify(evidence.project_id, commit))
        ov_receipt = self._try(
            lambda: self.openviking.ingest_commit(
                evidence.project_id, self.git.source_uri, commit, markdown
            )
        )

        ready = bool(qmd_receipt and ov_receipt)
        sync = KnowledgeSync(
            id=new_uuid7(),
            task_id=evidence.task_id,
            canonical_commit=commit,
            state="complete" if ready else "recovery_required",
            ready_for_cleanup=ready,
            qmd_receipt=qmd_receipt,
            qmd_collection=evidence.project_id if qmd_receipt else None,
            qmd_source_commit=commit if qmd_receipt else None,
            openviking_receipt=ov_receipt,
            openviking_uri=self.git.source_uri if ov_receipt else None,
            openviking_source_commit=commit if ov_receipt else None,
        )
        return self.store.save_knowledge_sync(sync)

    @staticmethod
    def _try(action: Callable[[], str]) -> str | None:
        try:
            return action()
        except Exception:
            return None
