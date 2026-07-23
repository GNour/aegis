# Core Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested local Aegis service with typed records, transactional state, tamper-evident audit, versioned flows, policy decisions, approvals, and a Unix-socket API.

**Architecture:** Python 3.12 packages keep domain types pure, place SQLite and JSONL behind ports, compile configuration into immutable snapshots, and expose commands through FastAPI on a Unix socket. State mutations write an audit outbox in the same transaction; a flusher appends the canonical ledger.

**Tech Stack:** Python 3.12, uv, Pydantic v2, FastAPI, Uvicorn, PyYAML, SQLite, Typer, pytest, Hypothesis, Ruff, mypy

---

### Task 1: Python project and verification shell

**Files:**
- Create: `pyproject.toml`
- Create: `src/aegis/__init__.py`
- Create: `src/aegis/cli.py`
- Create: `tests/test_cli.py`

- [x] **Step 1: Write the failing CLI test**

```python
from typer.testing import CliRunner

from aegis.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "aegis 0.1.0-dev"
```

- [x] **Step 2: Run the test and confirm collection fails**

Run: `uv run pytest tests/test_cli.py -q`

Expected: FAIL because `aegis.cli` does not exist.

- [x] **Step 3: Add the package metadata and minimal CLI**

```toml
[project]
name = "aegis-control-plane"
version = "0.1.0.dev0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.116,<1",
  "httpx>=0.28,<1",
  "pydantic>=2.11,<3",
  "pyyaml>=6.0,<7",
  "structlog>=25.4,<26",
  "typer>=0.16,<1",
  "uvicorn>=0.35,<1",
]

[dependency-groups]
dev = [
  "hypothesis>=6.138,<7",
  "mypy>=1.17,<2",
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.1,<2",
  "ruff>=0.12,<1",
]

[project.scripts]
aegis = "aegis.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aegis"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers --strict-config"
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["aegis"]
```

```python
# src/aegis/cli.py
import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo("aegis 0.1.0-dev")
```

- [x] **Step 4: Lock and verify the shell**

Run: `uv lock && uv run pytest tests/test_cli.py -q && uv run ruff check . && uv run mypy src`

Expected: one test passes; Ruff and mypy exit 0.

- [x] **Step 5: Commit the foundation**

```bash
git add pyproject.toml uv.lock src/aegis tests/test_cli.py
git commit -m "build(core): initialize aegis python project"
```

### Task 2: Domain records and legal task transitions

**Files:**
- Create: `src/aegis/domain/ids.py`
- Create: `src/aegis/domain/models.py`
- Create: `src/aegis/domain/state.py`
- Create: `tests/unit/domain/test_state.py`

- [x] **Step 1: Write transition tests**

```python
import pytest

from aegis.domain.state import TaskState, assert_transition


def test_normal_and_wait_transitions_are_legal() -> None:
    assert_transition(TaskState.INTAKE, TaskState.CLARIFY)
    assert_transition(TaskState.EXECUTING, TaskState.WAITING_QUOTA)
    assert_transition(TaskState.WAITING_QUOTA, TaskState.EXECUTING)


def test_complete_cannot_return_to_execution() -> None:
    with pytest.raises(ValueError, match="illegal task transition"):
        assert_transition(TaskState.COMPLETE, TaskState.EXECUTING)
```

- [x] **Step 2: Run the focused test and observe missing modules**

Run: `uv run pytest tests/unit/domain/test_state.py -q`

Expected: FAIL during import.

- [x] **Step 3: Implement strict IDs, records, and transition table**

```python
# src/aegis/domain/state.py
from enum import StrEnum


class TaskState(StrEnum):
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


_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.INTAKE: frozenset({TaskState.CLARIFY, TaskState.CANCELLED}),
    TaskState.CLARIFY: frozenset({TaskState.PLANNED, TaskState.WAITING_HUMAN, TaskState.CANCELLED}),
    TaskState.PLANNED: frozenset({TaskState.READY, TaskState.WAITING_HUMAN, TaskState.CANCELLED}),
    TaskState.READY: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.EXECUTING: frozenset({TaskState.VERIFYING, TaskState.WAITING_HUMAN, TaskState.WAITING_QUOTA, TaskState.WAITING_PROVIDER, TaskState.RETRY_SCHEDULED, TaskState.BLOCKED, TaskState.RECOVERY_REQUIRED, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.VERIFYING: frozenset({TaskState.REVIEWING, TaskState.EXECUTING, TaskState.RECOVERY_REQUIRED, TaskState.FAILED}),
    TaskState.REVIEWING: frozenset({TaskState.PRESERVING, TaskState.EXECUTING, TaskState.WAITING_HUMAN, TaskState.FAILED}),
    TaskState.PRESERVING: frozenset({TaskState.CLEANING, TaskState.RECOVERY_REQUIRED}),
    TaskState.CLEANING: frozenset({TaskState.COMPLETE, TaskState.RECOVERY_REQUIRED}),
    TaskState.WAITING_HUMAN: frozenset({TaskState.CLARIFY, TaskState.READY, TaskState.EXECUTING, TaskState.REVIEWING, TaskState.CANCELLED}),
    TaskState.WAITING_QUOTA: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.WAITING_PROVIDER: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.RETRY_SCHEDULED: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.BLOCKED: frozenset({TaskState.EXECUTING, TaskState.CANCELLED}),
    TaskState.RECOVERY_REQUIRED: frozenset({TaskState.EXECUTING, TaskState.PRESERVING, TaskState.CLEANING, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.COMPLETE: frozenset(),
    TaskState.CANCELLED: frozenset(),
    TaskState.FAILED: frozenset(),
}


def assert_transition(current: TaskState, target: TaskState) -> None:
    if target not in _ALLOWED[current]:
        raise ValueError(f"illegal task transition: {current} -> {target}")
```

Define `TaskManifest`, `FlowRun`, `StageRun`, `Attempt`, `DecisionRequest`,
`ApprovalRequest`, `SessionLink`, `HandoffPacket`, `ArtifactRecord`,
`KnowledgeSync`, `CleanupRecord`, and `AuditEvent` in `models.py` as Pydantic
models with `ConfigDict(extra="forbid", frozen=True)` and the exact required
fields from `docs/specs/01-domain-and-control-api.md`.

- [x] **Step 4: Verify domain behavior and typing**

Run: `uv run pytest tests/unit/domain -q && uv run mypy src/aegis/domain`

Expected: all domain tests pass and mypy exits 0.

- [x] **Step 5: Commit the domain**

```bash
git add src/aegis/domain tests/unit/domain
git commit -m "feat(domain): define task records and lifecycle"
```

### Task 3: SQLite store, migrations, and idempotent command transaction

**Files:**
- Create: `src/aegis/storage/schema/0001_initial.sql`
- Create: `src/aegis/storage/sqlite.py`
- Create: `tests/unit/storage/test_sqlite.py`

- [x] **Step 1: Write the idempotency test**

```python
from aegis.storage.sqlite import SQLiteStore


def test_same_idempotency_key_returns_original_result(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    first = store.create_task("key-1", {"request": "fix bug"})
    second = store.create_task("key-1", {"request": "fix bug"})
    assert second == first
    assert store.count_tasks() == 1
```

- [x] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/unit/storage/test_sqlite.py -q`

Expected: FAIL because the store is missing.

- [x] **Step 3: Implement migration and transaction boundary**

Create SQL tables for every authoritative record, `idempotency_records`,
`audit_outbox`, and `schema_migrations`. Enable `PRAGMA journal_mode=WAL`,
`PRAGMA foreign_keys=ON`, and `PRAGMA synchronous=FULL` on initialization.

```python
# src/aegis/storage/sqlite.py
import json
import sqlite3
from pathlib import Path
from uuid import uuid4


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(Path(__file__).with_name("schema").joinpath("0001_initial.sql").read_text())

    def create_task(self, key: str, payload: dict[str, str]) -> dict[str, str]:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self.connection:
            prior = self.connection.execute("SELECT request_json, response_json FROM idempotency_records WHERE key = ?", (key,)).fetchone()
            if prior:
                if prior["request_json"] != encoded:
                    raise ValueError("idempotency key reused with different payload")
                return json.loads(prior["response_json"])
            response = {"task_id": str(uuid4()), "state": "intake"}
            self.connection.execute("INSERT INTO tasks(id, state, version, request_json) VALUES (?, 'intake', 1, ?)", (response["task_id"], encoded))
            self.connection.execute("INSERT INTO idempotency_records(key, request_json, response_json) VALUES (?, ?, ?)", (key, encoded, json.dumps(response, sort_keys=True)))
            return response

    def count_tasks(self) -> int:
        return int(self.connection.execute("SELECT count(*) FROM tasks").fetchone()[0])
```

- [x] **Step 4: Verify persistence and property tests**

Run: `uv run pytest tests/unit/storage -q`

Expected: idempotency, conflicting-body, WAL, foreign-key, and migration tests pass.

- [x] **Step 5: Commit storage**

```bash
git add src/aegis/storage tests/unit/storage
git commit -m "feat(storage): add transactional sqlite state"
```

### Task 4: Redacted hash-linked audit ledger and outbox flusher

**Files:**
- Create: `src/aegis/audit/redaction.py`
- Create: `src/aegis/audit/ledger.py`
- Create: `tests/security/test_audit_redaction.py`
- Create: `tests/unit/audit/test_ledger.py`

- [x] **Step 1: Write redaction and tamper tests**

```python
from aegis.audit.ledger import Ledger


def test_secret_is_redacted_before_hashing(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    ledger.append("task.created", {"authorization": "Bear" + "er secret-value"})
    text = (tmp_path / "audit.jsonl").read_text()
    assert "secret-value" not in text
    assert ledger.verify() == []


def test_modified_event_breaks_chain(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    ledger.append("one", {"value": 1})
    ledger.append("two", {"value": 2})
    path = tmp_path / "audit.jsonl"
    path.write_text(path.read_text().replace('"value":1', '"value":9'))
    assert ledger.verify() == [1]
```

- [x] **Step 2: Confirm both tests fail**

Run: `uv run pytest tests/unit/audit tests/security/test_audit_redaction.py -q`

Expected: FAIL because ledger modules are missing.

- [x] **Step 3: Implement canonical redaction and chaining**

Use a recursive redactor with case-insensitive exact sensitive keys and compiled
token patterns. Serialize with `json.dumps(..., sort_keys=True,
separators=(",", ":"))`. Hash UTF-8 bytes containing event version, sequence,
prior hash, type, and redacted payload. Flush and `os.fsync` after each append.
Implement `flush_outbox(store, ledger)` to append committed outbox rows in
sequence and mark each flushed in a new transaction.

- [x] **Step 4: Run audit and storage suites**

Run: `uv run pytest tests/unit/audit tests/unit/storage tests/security/test_audit_redaction.py -q`

Expected: all tests pass, including process-restart outbox recovery.

- [x] **Step 5: Commit audit durability**

```bash
git add src/aegis/audit src/aegis/storage tests/unit/audit tests/unit/storage tests/security
git commit -m "feat(audit): add redacted hash-linked event ledger"
```

Before Task 5, execute the
[companion packages and stage packets plan](01a-companion-packages-and-stage-packets.md).
Flow compilation must reference its admitted companion lock, compiled role
catalog, and immutable packet contracts.

### Task 5: Flow catalog, routing, simulator, and atomic reload

**Files:**
- Create: `src/aegis/config/models.py`
- Create: `src/aegis/config/catalog.py`
- Create: `src/aegis/config/simulate.py`
- Create: `config/flows/feature-delivery.yaml`
- Create: `config/routing.yaml`
- Create: `tests/unit/config/test_catalog.py`

- [ ] **Step 1: Write snapshot and failed-reload tests**

```python
from aegis.config.catalog import CatalogManager


def test_task_snapshot_survives_reload(config_dir) -> None:
    manager = CatalogManager.load(config_dir)
    snapshot = manager.current.flow("feature-delivery").snapshot()
    config_dir.joinpath("flows/feature-delivery.yaml").write_text("invalid: true")
    assert manager.reload() is False
    assert manager.current.flow("feature-delivery").snapshot() == snapshot
```

- [ ] **Step 2: Run the config test and observe failure**

Run: `uv run pytest tests/unit/config/test_catalog.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement strict config models and catalog swap**

Create frozen Pydantic models for model aliases, capabilities, roles, stages,
flows, and routing rules. Reject unknown keys, duplicate IDs/versions, unresolved
references, arbitrary command fields, cycles, and missing mandatory gates. Build
the new `Catalog` fully, calculate canonical hashes, then assign it under one
lock. Add `ae config validate` and `ae flow simulate` Typer commands.

- [ ] **Step 4: Verify fixtures, CLI, and deterministic output**

Run: `uv run pytest tests/unit/config -q && uv run ae config validate --root config && uv run ae flow simulate --root config --fixture tests/fixtures/requests/feature.json`

Expected: tests pass; validation reports the catalog hash; simulation reports the
feature flow, its stages, capabilities, budgets, and routing rule IDs.

- [ ] **Step 5: Commit configuration engine**

```bash
git add src/aegis/config config tests/unit/config tests/fixtures src/aegis/cli.py
git commit -m "feat(flows): add versioned catalog and routing simulator"
```

### Task 6: Policy, one-use approvals, and Unix-socket API

**Files:**
- Create: `src/aegis/policy/engine.py`
- Create: `src/aegis/policy/approvals.py`
- Create: `src/aegis/api/app.py`
- Create: `src/aegis/api/auth.py`
- Create: `tests/security/test_approval_replay.py`
- Create: `tests/integration/api/test_tasks.py`

- [ ] **Step 1: Write API idempotency and approval-replay tests**

```python
def test_create_task_is_idempotent(client, signed_headers) -> None:
    body = {"project_id": "demo", "request": "add health route", "flow_id": "auto"}
    headers = signed_headers("POST", "/v1/tasks", body, idempotency_key="same")
    first = client.post("/v1/tasks", json=body, headers=headers)
    second = client.post("/v1/tasks", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]


def test_approval_token_cannot_be_replayed(client, approval, operator_headers) -> None:
    first = client.post(f"/v1/approvals/{approval.id}:approve", json=approval.payload, headers=operator_headers)
    second = client.post(f"/v1/approvals/{approval.id}:approve", json=approval.payload, headers=operator_headers)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "approval_replayed"
```

- [ ] **Step 2: Run the tests and confirm missing API**

Run: `uv run pytest tests/integration/api tests/security/test_approval_replay.py -q`

Expected: FAIL during import/fixture setup.

- [ ] **Step 3: Implement policy outcomes, signed assertions, and routes**

Implement the five outcomes from `docs/specs/02-flows-routing-policy.md`. Sign
principal assertions and approval payloads with HMAC-SHA256 over canonical JSON;
validate actor, operation, digest, issue/expiry, and nonce. Add only the nine
FR-001 operations. Require `Idempotency-Key` for mutations and return the stable
error contract from `docs/specs/01-domain-and-control-api.md`.

- [ ] **Step 4: Run full core verification**

Run: `uv run ruff check . && uv run mypy src && uv run pytest tests/unit tests/integration/api tests/security -q`

Expected: all core, API, policy, replay, redaction, and config tests pass.

- [ ] **Step 5: Commit the first vertical release**

```bash
git add src/aegis tests config
git commit -m "feat(api): expose policy-enforced local control plane"
```
