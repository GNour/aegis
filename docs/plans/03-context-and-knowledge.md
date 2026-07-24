# Context and Knowledge Implementation Plan

Status: implemented — all six tasks complete. Exact digest-verified read-only skill
bundles, scoped/bounded QMD retrieval, source-linked OpenViking memory, the bounded
cited context compiler, RTK dual-output capture with full-log retention, and the
preservation coordinator that gates cleanup on exact-commit QMD/OpenViking receipts
all pass (`uv run ruff check .`, `uv run pytest`, `uv run mypy src/aegis` clean
except the pre-existing Windows-only `audit/ledger.py` msvcrt errors). QMD and
OpenViking are not installed here, so their adapters are built against typed ports
with fakes per docs/rfcs/0005-qmd.md §5a and docs/rfcs/0003-openviking.md §5a.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver role-isolated skills, project-scoped QMD retrieval, source-linked OpenViking memory, bounded context compilation, RTK evidence, and a knowledge transaction that blocks cleanup until indexing receipts exist.

**Architecture:** Git Markdown is canonical. Read adapters return cited immutable records; the context compiler budgets and deduplicates them. A preservation coordinator commits knowledge first, then updates QMD and OpenViking and stores receipts atomically before unlocking cleanup.

**Tech Stack:** Python 3.12, QMD CLI/local MCP adapter, OpenViking HTTP API, Git, RTK, Pydantic, pytest

---

### Task 1: Exact skill resolver and ephemeral read-only bundle

**Files:**
- Create: `src/aegis/context/skills.py`
- Create: `tests/security/test_skill_isolation.py`

- [ ] **Step 1: Write role-isolation tests**

```python
def test_worker_receives_only_declared_skills(skill_registry, tmp_path) -> None:
    bundle = skill_registry.bundle({"tdd": "1.2.0", "backend": "2.0.1"}, tmp_path)
    assert sorted(path.name for path in bundle.iterdir()) == ["backend", "tdd"]
    assert not bundle.joinpath("deployment").exists()
    assert bundle.stat().st_mode & 0o222 == 0


def test_unknown_skill_version_fails_closed(skill_registry, tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown skill version"):
        skill_registry.bundle({"tdd": "99.0.0"}, tmp_path)
```

- [ ] **Step 2: Run and confirm missing resolver**

Run: `uv run pytest tests/security/test_skill_isolation.py -q`

Expected: FAIL during import/fixture creation.

- [ ] **Step 3: Implement digest-verified copying**

```python
import os
import shutil
from pathlib import Path


class SkillRegistry:
    def __init__(self, root: Path, manifest: dict[str, dict[str, str]]) -> None:
        self.root, self.manifest = root.resolve(), manifest

    def bundle(self, requested: dict[str, str], destination: Path) -> Path:
        destination.mkdir(mode=0o700, parents=True)
        for skill_id, version in sorted(requested.items()):
            record = self.manifest.get(skill_id)
            if record is None or record["version"] != version:
                raise ValueError(f"unknown skill version: {skill_id}@{version}")
            source = (self.root / record["path"]).resolve()
            if not source.is_relative_to(self.root):
                raise ValueError("skill path escapes registry")
            shutil.copytree(source, destination / skill_id)
        for path in [destination, *destination.rglob("*")]:
            os.chmod(path, 0o500 if path.is_dir() else 0o400)
        return destination
```

Verify SHA-256 digests from the registry manifest before copying and store the
resolved digest map in the stage snapshot.

- [ ] **Step 4: Run security tests**

Run: `uv run pytest tests/security/test_skill_isolation.py -q`

Expected: undeclared, unknown-version, digest-mismatch, traversal, and write probes fail.

- [ ] **Step 5: Commit skill isolation**

```bash
git add src/aegis/context/skills.py tests/security/test_skill_isolation.py
git commit -m "feat(context): inject exact read-only role skills"
```

### Task 2: QMD collection ACL and bounded retrieval adapter

**Files:**
- Create: `src/aegis/knowledge/qmd.py`
- Create: `tests/security/test_qmd_acl.py`
- Create: `tests/contract/test_qmd_adapter.py`

- [ ] **Step 1: Write collection and parameter tests**

```python
def test_project_cannot_search_other_collection(qmd, task_scope) -> None:
    with pytest.raises(PermissionError, match="collection not allowed"):
        qmd.search(task_scope, collection="project-b", query="secrets", limit=5)


def test_qmd_limit_is_bounded(qmd, task_scope) -> None:
    with pytest.raises(ValueError, match="limit"):
        qmd.search(task_scope, collection="project-a", query="routes", limit=101)
```

- [ ] **Step 2: Run and observe adapter absence**

Run: `uv run pytest tests/security/test_qmd_acl.py tests/contract/test_qmd_adapter.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement strict argument construction**

```python
from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class RetrievalScope:
    task_id: str
    collections: frozenset[str]
    modes: frozenset[str]


class QmdAdapter:
    def search(self, scope: RetrievalScope, collection: str, query: str, limit: int = 8, mode: str = "lexical") -> list[dict[str, object]]:
        if collection not in scope.collections:
            raise PermissionError("collection not allowed")
        if mode not in scope.modes:
            raise PermissionError("search mode not allowed")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        result = subprocess.run(["qmd", "search", query, "-c", collection, "--json", "-n", str(limit)], check=True, capture_output=True, text=True)
        return validate_results(result.stdout, collection, limit)
```

`validate_results` parses a list, rejects unknown fields and foreign collection
URIs, truncates snippet bytes, and records query mode/collection/result URIs. The
adapter owns configuration; it never runs collection update hooks from a project.

- [ ] **Step 4: Run ACL and recorded-contract tests**

Run: `uv run pytest tests/security/test_qmd_acl.py tests/contract/test_qmd_adapter.py -q`

Expected: authorized lexical results include cited URIs; all ACL, unknown-parameter, traversal, and excessive-limit cases fail.

- [ ] **Step 5: Commit QMD retrieval**

```bash
git add src/aegis/knowledge/qmd.py tests/security/test_qmd_acl.py tests/contract/test_qmd_adapter.py
git commit -m "feat(knowledge): add scoped qmd retrieval"
```

### Task 3: OpenViking source-linked memory adapter

**Files:**
- Create: `src/aegis/knowledge/openviking.py`
- Create: `tests/contract/test_openviking_adapter.py`

- [ ] **Step 1: Write source-commit enforcement tests**

```python
def test_memory_without_source_commit_is_excluded(openviking) -> None:
    openviking.transport.responses = [{"uri": "viking://m/1", "text": "fact", "metadata": {"project_id": "a"}}]
    assert openviking.recall(project_id="a", query="fact", limit=5) == []


def test_foreign_project_memory_is_excluded(openviking) -> None:
    openviking.transport.responses = [{"uri": "viking://m/2", "text": "fact", "metadata": {"project_id": "b", "source_commit": "abc", "source_uri": "git://brain/a.md"}}]
    assert openviking.recall(project_id="a", query="fact", limit=5) == []
```

- [ ] **Step 2: Confirm contract test failure**

Run: `uv run pytest tests/contract/test_openviking_adapter.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement authenticated loopback client and filter**

```python
class OpenVikingAdapter:
    def __init__(self, transport) -> None:
        self.transport = transport

    def recall(self, project_id: str, query: str, limit: int) -> list[dict[str, object]]:
        raw = self.transport.post("/api/v1/search", json={"query": query, "limit": min(limit, 20)})
        return [
            item for item in raw
            if item.get("metadata", {}).get("project_id") == project_id
            and item.get("metadata", {}).get("source_commit")
            and item.get("metadata", {}).get("source_uri")
        ]

    def ingest_commit(self, project_id: str, source_uri: str, commit: str, markdown: str) -> str:
        result = self.transport.post("/api/v1/resources", json={"project_id": project_id, "source_uri": source_uri, "source_commit": commit, "content": markdown})
        return str(result["receipt_id"])
```

Construct the production transport with a loopback base URL, API-key header loaded
from an `agentops`-owned file, bounded timeouts, and readiness check. Redact the
header from exceptions and logs.

- [ ] **Step 4: Run recorded response and error tests**

Run: `uv run pytest tests/contract/test_openviking_adapter.py -q`

Expected: source/project filters, timeout mapping, readiness, ingestion receipt, and redaction tests pass.

- [ ] **Step 5: Commit OpenViking adapter**

```bash
git add src/aegis/knowledge/openviking.py tests/contract/test_openviking_adapter.py
git commit -m "feat(knowledge): add source-linked openviking memory"
```

### Task 4: Bounded context compiler

**Files:**
- Create: `src/aegis/context/models.py`
- Create: `src/aegis/context/compiler.py`
- Create: `tests/unit/context/test_compiler.py`

- [ ] **Step 1: Write budget and deduplication tests**

```python
def test_context_is_bounded_and_deduplicated(compiler, request) -> None:
    envelope = compiler.compile(request, max_bytes=4096)
    assert envelope.total_bytes <= 4096
    digests = [item.digest for section in envelope.sections for item in section.items]
    assert len(digests) == len(set(digests))
    assert envelope.sections[0].name == "stage_contract"


def test_full_transcript_is_not_a_default_source(compiler, request) -> None:
    envelope = compiler.compile(request, max_bytes=4096)
    assert all(item.kind != "raw_transcript" for section in envelope.sections for item in section.items)
```

- [ ] **Step 2: Run and confirm compiler absence**

Run: `uv run pytest tests/unit/context/test_compiler.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement ordered selection**

```python
class ContextCompiler:
    ORDER = ("stage_contract", "acceptance", "decisions", "handoff", "skills", "files", "qmd", "openviking")

    def compile(self, request, max_bytes: int):
        seen: set[str] = set()
        remaining = max_bytes
        sections = []
        for name in self.ORDER:
            kept = []
            for item in self.sources[name](request):
                if item.digest in seen or item.byte_size > remaining:
                    continue
                kept.append(item)
                seen.add(item.digest)
                remaining -= item.byte_size
            if kept:
                sections.append(ContextSection(name=name, items=kept))
        return ContextEnvelope(sections=sections, total_bytes=max_bytes - remaining, budget_bytes=max_bytes)
```

Define frozen Pydantic `ContextItem`, `ContextSection`, and `ContextEnvelope`
models containing kind, content, source URI, digest, and byte/token estimates.

- [ ] **Step 4: Run compiler and property tests**

Run: `uv run pytest tests/unit/context -q`

Expected: ordering, deduplication, per-source ceilings, total ceiling, citation, and empty-source cases pass.

- [ ] **Step 5: Commit bounded context**

```bash
git add src/aegis/context tests/unit/context
git commit -m "feat(context): compile bounded cited worker context"
```

### Task 5: RTK compressed output with complete artifact retention

**Files:**
- Create: `src/aegis/execution/output.py`
- Create: `tests/unit/execution/test_output_capture.py`

- [ ] **Step 1: Write dual-output tests**

```python
def test_model_receives_compressed_output_and_artifact_keeps_full_text(capture, tmp_path) -> None:
    result = capture.record(command_id="c1", full="100 passed\n" * 100, compressed="100 passed")
    assert result.model_text == "100 passed"
    assert result.full_artifact.read_text() == "100 passed\n" * 100
    assert result.saved_bytes > 0
```

- [ ] **Step 2: Run and confirm capture absence**

Run: `uv run pytest tests/unit/execution/test_output_capture.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement protected full output and metrics**

```python
class OutputCapture:
    def __init__(self, artifact_store) -> None:
        self.artifact_store = artifact_store

    def record(self, command_id: str, full: str, compressed: str):
        artifact = self.artifact_store.write_text(f"commands/{command_id}.log", full, mode=0o600)
        return CapturedOutput(model_text=compressed, full_artifact=artifact, full_bytes=len(full.encode()), model_bytes=len(compressed.encode()), saved_bytes=max(0, len(full.encode()) - len(compressed.encode())))
```

The worker image calls pinned RTK for supported commands. Aegis stores the raw
process stream before compression and records RTK version and savings in `Attempt`.

- [ ] **Step 4: Verify output, redaction, and artifact digest tests**

Run: `uv run pytest tests/unit/execution/test_output_capture.py tests/security/test_audit_redaction.py -q`

Expected: complete output is protected and digested; model output and metrics are bounded; secrets are redacted from summaries.

- [ ] **Step 5: Commit RTK evidence path**

```bash
git add src/aegis/execution/output.py tests/unit/execution/test_output_capture.py
git commit -m "feat(tokens): retain full logs and measure rtk savings"
```

### Task 6: Knowledge preservation coordinator and cleanup lock

**Files:**
- Create: `src/aegis/knowledge/preserve.py`
- Create: `tests/integration/knowledge/test_preservation.py`
- Create: `tests/recovery/test_preservation_failure.py`

- [ ] **Step 1: Write exact-commit and failure tests**

```python
def test_both_receipts_reference_committed_source(coordinator, completed_evidence) -> None:
    sync = coordinator.preserve(completed_evidence)
    assert sync.qmd_source_commit == sync.canonical_commit
    assert sync.openviking_source_commit == sync.canonical_commit
    assert sync.ready_for_cleanup is True


def test_openviking_failure_keeps_cleanup_locked(coordinator, completed_evidence, openviking) -> None:
    openviking.fail_next = True
    sync = coordinator.preserve(completed_evidence)
    assert sync.ready_for_cleanup is False
    assert sync.state == "recovery_required"
```

- [ ] **Step 2: Confirm preservation tests fail**

Run: `uv run pytest tests/integration/knowledge tests/recovery/test_preservation_failure.py -q`

Expected: FAIL because the coordinator is absent.

- [ ] **Step 3: Implement ordered preservation**

```python
class PreservationCoordinator:
    def preserve(self, evidence):
        markdown = self.renderer.render(evidence)
        commit = self.git.commit(markdown, message=f"docs(task): preserve {evidence.task_id}")
        qmd_receipt = self.qmd.update_and_verify(evidence.project_id, commit)
        ov_receipt = self.openviking.ingest_commit(evidence.project_id, self.git.source_uri, commit, markdown)
        sync = KnowledgeSync(canonical_commit=commit, qmd_receipt=qmd_receipt, qmd_source_commit=commit, openviking_receipt=ov_receipt, openviking_source_commit=commit, state="complete", ready_for_cleanup=True)
        return self.store.save_knowledge_sync(sync)
```

Wrap adapter failures into a persisted partial `KnowledgeSync` with
`ready_for_cleanup=False`; never roll back the Git commit or delete task resources.
On resume, reuse the canonical commit and retry only missing/invalid receipts.

- [ ] **Step 4: Run knowledge, cleanup, and recovery suites**

Run: `uv run pytest tests/integration/knowledge tests/recovery tests/security/test_qmd_acl.py -q`

Expected: exact-commit receipts pass; each injected failure remains recoverable and blocks cleanup.

- [ ] **Step 5: Commit the knowledge gate**

```bash
git add src/aegis/knowledge tests/integration/knowledge tests/recovery
git commit -m "feat(knowledge): preserve canonical context before cleanup"
```
