---
title: Workers, Herdr, and Project Services Implementation Plan
tags:
  - aegis
  - plan
  - workers
---

# Workers, Herdr, and Project Services Implementation Plan

Status: implemented — all six tasks complete. Trusted project manifests, contained
Git worktrees, rootless task-scoped services with exact-label cleanup, the narrow
Herdr socket adapter (validated against a deterministic fake; live probe gated on
`HERDR_SOCKET`), task-scoped worker sandboxes with a credential non-exposure canary
gate, and failure classification with native-first resume and preservation-gated
cleanup all pass (`uv run ruff check .`, `uv run pytest`, `uv run mypy src/aegis`
clean except the pre-existing Windows-only `audit/ledger.py` msvcrt errors). Because
Herdr is not yet installed, the adapter is built against a typed port with a fake
per docs/rfcs/0002-herdr.md §5a.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute one writing worker per isolated Git worktree with rootless project services, durable Herdr/native sessions, classified failure recovery, and exact-label cleanup.

**Architecture:** Core orchestration calls ports for Git, Herdr, runtime, service, and artifact operations. Production adapters use argument arrays and structured results; tests use deterministic fakes. Task resources carry an immutable label/nonce set, and cleanup requires preservation preconditions from the state store.

**Tech Stack:** Python 3.12, asyncio, subprocess argument arrays, Herdr socket/CLI adapter, Git, rootless Docker/Compose, pytest

---

### Task 1: Trusted project manifest schema

**Files:**
- Create: `src/aegis/execution/project_manifest.py`
- Create: `config/schemas/project-v1.json`
- Create: `tests/security/test_project_manifest.py`

- [ ] **Step 1: Write rejection tests**

```python
import pytest
from pydantic import ValidationError

from aegis.execution.project_manifest import ProjectManifest


@pytest.mark.parametrize("service", [
    {"image": "postgres:17", "privileged": True},
    {"image": "postgres:17", "network_mode": "host"},
    {"image": "postgres:17", "devices": ["/dev/kvm"]},
    {"image": "postgres:17", "volumes": ["/etc:/host"]},
])
def test_dangerous_service_fields_are_rejected(service) -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"version": 1, "commands": {}, "services": {"db": service}})


def test_commands_are_argument_arrays() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"version": 1, "commands": {"test": "pytest && curl evil"}})
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `uv run pytest tests/security/test_project_manifest.py -q`

Expected: FAIL because the manifest model is absent.

- [ ] **Step 3: Implement the strict schema**

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_mb: int = Field(ge=64, le=8192)
    cpus: float = Field(gt=0, le=4)


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    image: str
    environment: dict[str, str] = {}
    healthcheck: list[str]
    container_port: int = Field(ge=1, le=65535)
    limits: Limits


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(ge=1, le=1)
    commands: dict[str, list[str]]
    services: dict[str, Service] = {}
    artifact_globs: list[str] = []

    @field_validator("commands")
    @classmethod
    def nonempty_argv(cls, commands: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(not argv or any("\x00" in item for item in argv) for argv in commands.values()):
            raise ValueError("commands require nonempty NUL-free argument arrays")
        return commands
```

Generate `project-v1.json` with `ProjectManifest.model_json_schema()` in a checked
CLI command and compare the generated object to the committed file in a test.

- [ ] **Step 4: Verify positive and negative manifest fixtures**

Run: `uv run pytest tests/security/test_project_manifest.py -q`

Expected: dangerous fields and shell strings fail; the sanitized fixture passes.

- [ ] **Step 5: Commit manifest validation**

```bash
git add src/aegis/execution config/schemas tests/security
git commit -m "feat(execution): validate trusted project manifests"
```

### Task 2: Git worktree manager with path containment

**Files:**
- Create: `src/aegis/execution/command.py`
- Create: `src/aegis/execution/worktrees.py`
- Create: `tests/security/test_worktree_paths.py`

- [ ] **Step 1: Write traversal and branch tests**

```python
import pytest

from aegis.execution.worktrees import WorktreeManager


def test_task_path_stays_under_root(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    with pytest.raises(ValueError, match="invalid task id"):
        manager.path_for("../../escape")


def test_branch_is_derived_from_task_id(tmp_path) -> None:
    manager = WorktreeManager(tmp_path / "root")
    assert manager.branch_for("018f8bd9-19d6-7902-9018-593c0a97ea8a", "Fix Login") == "task/018f8bd9-fix-login"
```

- [ ] **Step 2: Confirm the test fails**

Run: `uv run pytest tests/security/test_worktree_paths.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement argument-array Git operations**

```python
import re
import subprocess
from pathlib import Path


class WorktreeManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, task_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}", task_id):
            raise ValueError("invalid task id")
        path = (self.root / task_id).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("worktree path escapes root")
        return path

    def branch_for(self, task_id: str, slug: str) -> str:
        safe = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40]
        return f"task/{task_id[:8]}-{safe}"

    def create(self, repo: Path, base: str, task_id: str, slug: str) -> tuple[Path, str]:
        path, branch = self.path_for(task_id), self.branch_for(task_id, slug)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", branch, str(path), base], check=True)
        return path, branch

    def remove(self, repo: Path, task_id: str) -> None:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", str(self.path_for(task_id))], check=True)
```

- [ ] **Step 4: Run worktree integration fixtures**

Run: `uv run pytest tests/security/test_worktree_paths.py tests/integration/execution/test_worktrees.py -q`

Expected: traversal and symlink escape fail; create/remove succeeds in a temporary Git repository.

- [ ] **Step 5: Commit the worktree manager**

```bash
git add src/aegis/execution tests/security tests/integration/execution
git commit -m "feat(execution): manage contained git worktrees"
```

### Task 3: Rootless service labels, ports, and exact cleanup

**Files:**
- Create: `src/aegis/execution/resources.py`
- Create: `src/aegis/execution/services.py`
- Create: `tests/security/test_resource_cleanup.py`

- [ ] **Step 1: Write the no-global-cleanup test**

```python
from aegis.execution.resources import ResourceIdentity
from aegis.execution.services import FakeServiceRuntime


def test_cleanup_removes_only_matching_identity() -> None:
    runtime = FakeServiceRuntime()
    ours = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    other = ResourceIdentity(instance="pilot", task_id="task-b", nonce="n2")
    runtime.seed(ours)
    runtime.seed(other)
    runtime.cleanup(ours)
    assert runtime.exists(ours) is False
    assert runtime.exists(other) is True
    assert "prune" not in runtime.commands
```

- [ ] **Step 2: Confirm missing resource modules**

Run: `uv run pytest tests/security/test_resource_cleanup.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement immutable identity and runtime port**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceIdentity:
    instance: str
    task_id: str
    nonce: str

    def labels(self) -> dict[str, str]:
        return {
            "dev.aegis.instance": self.instance,
            "dev.aegis.task": self.task_id,
            "dev.aegis.nonce": self.nonce,
            "dev.aegis.managed": "true",
        }

    @property
    def compose_project(self) -> str:
        return f"aegis_{self.task_id.replace('-', '')[:16]}_{self.nonce[:8]}"
```

The production `ComposeServiceRuntime` renders an Aegis-owned Compose override,
runs `docker --context aegis-rootless compose --project-name <exact> up -d
--wait`, lists resources by all identity labels, compares nonce/labels before
removal, and runs only `compose down --volumes --remove-orphans` for that project.

- [ ] **Step 4: Verify fake and rootless integration scenarios**

Run: `uv run pytest tests/security/test_resource_cleanup.py tests/integration/execution/test_services.py -q`

Expected: other-task and unlabeled fixtures survive; exact task resources disappear.

- [ ] **Step 5: Commit service isolation**

```bash
git add src/aegis/execution tests/security tests/integration/execution
git commit -m "feat(execution): isolate task project services"
```

### Task 4: Herdr adapter and native session correlation

**Files:**
- Create: `src/aegis/execution/herdr.py`
- Create: `tests/contract/test_herdr_adapter.py`
- Create: `tests/fixtures/herdr/schema.json`

- [ ] **Step 1: Write contract tests against recorded responses**

```python
from aegis.execution.herdr import HerdrClient


def test_start_returns_both_session_identifiers(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    session = client.start(agent="opencode", cwd="/tasks/t1", argv=["opencode", "run"])
    assert session.herdr_id == "pane-17"
    assert session.native_id == "ses_123"


def test_unknown_protocol_is_rejected(fake_herdr) -> None:
    fake_herdr.protocol_version = "99"
    client = HerdrClient(fake_herdr.socket_path)
    assert client.compatible() is False
```

- [ ] **Step 2: Confirm contract test failure**

Run: `uv run pytest tests/contract/test_herdr_adapter.py -q`

Expected: FAIL because the adapter is missing.

- [ ] **Step 3: Implement the narrow protocol adapter**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentSession:
    herdr_id: str
    native_id: str | None
    state: str


class HerdrClient:
    SUPPORTED_PROTOCOLS = frozenset({"1"})

    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path

    def compatible(self) -> bool:
        return self.schema()["protocol_version"] in self.SUPPORTED_PROTOCOLS

    def start(self, agent: str, cwd: str, argv: list[str]) -> AgentSession:
        response = self.request("agent.start", {"agent": agent, "cwd": cwd, "argv": argv})
        return AgentSession(response["session_id"], response.get("native_session_id"), response["state"])
```

Implement `schema`, `request`, `inspect`, `interrupt`, `resume`, and `remove` with
length-bounded JSON requests over the private Unix socket. Validate every response
with Pydantic and reject unsupported protocol versions before dispatch.

- [ ] **Step 4: Run contract tests and live-version probe when Herdr is installed**

Run: `uv run pytest tests/contract/test_herdr_adapter.py -q`

Expected: all recorded protocol fixtures pass. The optional live marker remains skipped unless `HERDR_SOCKET` points to a test instance.

- [ ] **Step 5: Commit Herdr integration**

```bash
git add src/aegis/execution/herdr.py tests/contract tests/fixtures/herdr
git commit -m "feat(herdr): correlate durable worker sessions"
```

### Task 5: Worker sandbox and credential non-exposure gate

**Files:**
- Create: `src/aegis/execution/workers.py`
- Create: `src/aegis/execution/sandbox.py`
- Create: `tests/security/test_worker_sandbox.py`

- [ ] **Step 1: Write the environment/mount/network assertions**

```python
def test_worker_spec_contains_only_scoped_inputs(worker_spec) -> None:
    assert set(worker_spec.environment) == {"AEGIS_TASK_ID", "MODEL_PROXY_URL", "MODEL_CAPABILITY"}
    assert all("OPENAI" not in key and "TOKEN" not in key for key in worker_spec.environment)
    assert worker_spec.network == "none"
    assert worker_spec.mounts == [("/tasks/t1", "/workspace", "rw"), ("/skills/s1", "/skills", "ro")]
    assert worker_spec.cap_drop == ["ALL"]
    assert worker_spec.no_new_privileges is True
```

- [ ] **Step 2: Run the security test and see it fail**

Run: `uv run pytest tests/security/test_worker_sandbox.py -q`

Expected: FAIL because `WorkerSpec` is absent.

- [ ] **Step 3: Implement the immutable worker specification**

```python
from pydantic import BaseModel, ConfigDict


class WorkerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    image: str
    argv: list[str]
    environment: dict[str, str]
    mounts: list[tuple[str, str, str]]
    network: str = "none"
    memory_mb: int
    cpus: float
    cap_drop: list[str] = ["ALL"]
    no_new_privileges: bool = True
    read_only_root: bool = True
```

Build OpenCode and Codex specs only from role/capability snapshots and a short-lived
model capability. The launch adapter renders rootless container arguments directly
from `WorkerSpec`; it never inherits the parent environment. Add a probe worker
that searches `/proc/self/environ`, mounted files, process arguments, exported
session, and artifact output for a seeded canary provider key.

- [ ] **Step 4: Run the sandbox/canary suite**

Run: `uv run pytest tests/security/test_worker_sandbox.py tests/integration/execution/test_worker_canary.py -q`

Expected: every canary location is clean; network and forbidden mount probes fail closed.

- [ ] **Step 5: Commit worker containment**

```bash
git add src/aegis/execution tests/security tests/integration/execution
git commit -m "feat(workers): enforce task-scoped rootless sandboxes"
```

### Task 6: Recovery classification, native resume, and cleanup gate

**Files:**
- Create: `src/aegis/execution/recovery.py`
- Create: `src/aegis/execution/cleanup.py`
- Create: `tests/recovery/test_resume.py`
- Create: `tests/recovery/test_cleanup_gate.py`

- [ ] **Step 1: Write quota and preservation-gate tests**

```python
from datetime import UTC, datetime


def test_credit_limit_waits_without_retry_loop(engine, credit_failure) -> None:
    result = engine.handle_failure(credit_failure)
    assert result.state == "waiting_quota"
    assert result.earliest_retry > datetime.now(UTC)
    assert result.dispatch_now is False


def test_cleanup_refuses_missing_knowledge_receipt(cleanup, completed_task) -> None:
    completed_task.knowledge_sync.openviking_receipt = None
    result = cleanup.run(completed_task)
    assert result.state == "recovery_required"
    assert result.deleted == []
```

- [ ] **Step 2: Confirm recovery tests fail**

Run: `uv run pytest tests/recovery -q`

Expected: FAIL because recovery and cleanup services are missing.

- [ ] **Step 3: Implement classification and ordered resume**

Create a total mapping from exit/provider signals to the failure table in
`docs/specs/05-recovery-audit-cleanup.md`. `ResumeService` calls Herdr/native
resume when the session is compatible; otherwise it validates the latest handoff
and creates a new attempt using the original stage snapshot. `CleanupService`
checks all FR-055–057 receipts before calling exact-label service and worktree
removal, then verifies absence and records `CleanupRecord`.

- [ ] **Step 4: Run execution, security, and recovery suites**

Run: `uv run pytest tests/integration/execution tests/security tests/recovery -q`

Expected: process-kill, quota wait, native resume, handoff fallback, orphan quarantine, and cleanup-gate cases pass.

- [ ] **Step 5: Commit durable execution**

```bash
git add src/aegis/execution tests/integration/execution tests/security tests/recovery
git commit -m "feat(recovery): resume workers and gate exact cleanup"
```
