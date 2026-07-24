# Companion Packages and Stage Packets Implementation Plan

Status: implemented — all eight tasks complete on branch `feat/companion-integration`.
Companions are pinned as HTTPS submodules with a digest-verified lock; the reviewed
role catalog and provenance are compiled and embedded; the bounded PromptX adapter,
immutable stage packets, insert-once storage, readiness gate, and adversarial/rollback
suites all pass (`uv run pytest`, `ruff`, `mypy`, and `tools/companions.py check`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin admitted PromptX and Subagents releases, compile an authority-free role catalog, call PromptX through a bounded broker-only adapter, and persist an immutable `StageExecutionPacket` before any future worker dispatch.

**Architecture:** Aegis treats both repositories as verified source inputs, never ambient tools. Build-time code validates the submodule pins and compiles selected Subagents data into immutable release assets; runtime code validates the installed PromptX artifact and produces a bounded enrichment. A pure packet compiler combines only validated snapshots, and the SQLite store inserts the canonical packet exactly once before a dispatcher may consume it.

**Tech Stack:** Python 3.12, uv, Pydantic v2, PyYAML, SQLite WAL, Git submodules, Node.js 20 for the admitted PromptX build, pytest, Hypothesis, Ruff, and mypy

---

## Entry gate

Do not start Task 1 until both upstream repositories satisfy the P0 items in
[`docs/maintainer-handoff-promptx-subagents.md`](../maintainer-handoff-promptx-subagents.md).
The accepted upstream commits must be on their repositories' normal history,
have package-local tests and release notes, and expose these commands:

```bash
npm --prefix packages/promptx ci
npm --prefix packages/promptx run check
npm --prefix packages/promptx run build
node packages/promptx/dist/cli/index.js aegis-contract --version-json

packages/subagents/bin/subagents-catalog validate
packages/subagents/bin/subagents-catalog generate --check
packages/subagents/bin/subagents-catalog version --json
```

Expected: every command exits `0`; the version commands return strict JSON with
the approved package/protocol or package/catalog-schema versions. If an upstream
command or contract differs, update the upstream repository and its handoff
evidence before changing this plan or adding an Aegis pin.

## File map

| Path | Responsibility |
|---|---|
| `.gitmodules` and `packages/` | HTTPS source pins; never runtime search paths |
| `config/companions.lock.json` | Canonical admitted source, contract, and artifact digests |
| `config/companions/role-mappings.yaml` | Reviewed mapping from advisory roles to Aegis authority |
| `src/aegis/companions/lock.py` | Lock parsing and clean/pinned submodule verification |
| `src/aegis/companions/subagents.py` | Strict upstream catalog and compiled-role contracts |
| `src/aegis/companions/catalog.py` | Deterministic, authority-removing catalog compiler |
| `src/aegis/companions/promptx.py` | Fixed JSON subprocess adapter and readiness verification |
| `src/aegis/domain/stage_packet.py` | Immutable packet/input models and canonical hashing |
| `src/aegis/engine/stage_packets.py` | The only assembly path from validated snapshots to packets |
| `src/aegis/storage/schema/0003_stage_execution_packets.sql` | Durable one-packet-per-stage record |
| `src/aegis/data/companions/` | Embedded compiled catalog and provenance assets |
| `tools/companions.py` | Build/check commands used by maintainers and CI |
| `tests/companions/fixtures/` | Valid, malicious, incompatible, and degraded contract fixtures |

### Task 1: Pin companions and reject unadmitted source state

**Files:**
- Create: `.gitmodules`
- Create: `packages/promptx` as a Git submodule
- Create: `packages/subagents` as a Git submodule
- Create: `config/companions.lock.json`
- Create: `src/aegis/companions/__init__.py`
- Create: `src/aegis/companions/lock.py`
- Create: `tests/unit/companions/test_lock.py`
- Create: `tests/security/test_companion_source_state.py`

- [ ] **Step 1: Write failing lock and source-state tests**

Define the contract before adding either submodule:

```python
from pathlib import Path

import pytest

from aegis.companions.lock import (
    CompanionLock,
    CompanionSourceError,
    GitResult,
    verify_sources,
)


def admitted_lock() -> CompanionLock:
    return CompanionLock.model_validate(
        {
            "schema_version": 1,
            "promptx": {
                "path": "packages/promptx",
                "source_url": "https://github.com/GNour/promptx.git",
                "source_commit": "a" * 40,
                "package_version": "1.0.0",
                "contract_version": "1",
                "artifact_sha256": "1" * 64,
                "sbom_sha256": "3" * 64,
                "license_spdx": "MIT",
            },
            "subagents": {
                "path": "packages/subagents",
                "source_url": "https://github.com/GNour/subagents.git",
                "source_commit": "b" * 40,
                "package_version": "1.0.0",
                "contract_version": "1",
                "artifact_sha256": "2" * 64,
                "sbom_sha256": "4" * 64,
                "license_spdx": "MIT",
            },
        }
    )


def test_clean_exact_sources_are_accepted(tmp_path: Path) -> None:
    lock = admitted_lock()

    def git(path: Path, *arguments: str) -> GitResult:
        if arguments == ("rev-parse", "HEAD"):
            commit = lock.promptx.source_commit if path.name == "promptx" else lock.subagents.source_commit
            return GitResult(returncode=0, stdout=commit + "\n", stderr="")
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return GitResult(returncode=0, stdout="", stderr="")
        raise AssertionError(arguments)

    verify_sources(tmp_path, lock, git=git, require_present=False)


@pytest.mark.parametrize(
    ("head", "status", "message"),
    [
        ("c" * 40, "", "source commit mismatch"),
        ("a" * 40, " M package.json\n", "dirty companion source"),
    ],
)
def test_promptx_advanced_or_dirty_source_is_rejected(
    tmp_path: Path, head: str, status: str, message: str
) -> None:
    lock = admitted_lock()

    def git(path: Path, *arguments: str) -> GitResult:
        if path.name == "promptx" and arguments == ("rev-parse", "HEAD"):
            return GitResult(returncode=0, stdout=head + "\n", stderr="")
        if path.name == "subagents" and arguments == ("rev-parse", "HEAD"):
            return GitResult(
                returncode=0,
                stdout=lock.subagents.source_commit + "\n",
                stderr="",
            )
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return GitResult(
                returncode=0,
                stdout=status if path.name == "promptx" else "",
                stderr="",
            )
        raise AssertionError(arguments)

    with pytest.raises(CompanionSourceError, match=message):
        verify_sources(tmp_path, lock, git=git, require_present=False)
```

- [ ] **Step 2: Run the tests and confirm the integration is absent**

Run:

```bash
uv run pytest tests/unit/companions/test_lock.py tests/security/test_companion_source_state.py -q
```

Expected: FAIL during collection because `aegis.companions.lock` does not
exist.

- [ ] **Step 3: Add HTTPS submodules at the accepted upstream commits**

Run:

```bash
git submodule add https://github.com/GNour/promptx.git packages/promptx
git submodule add https://github.com/GNour/subagents.git packages/subagents
git -C packages/promptx checkout --detach origin/main
git -C packages/subagents checkout --detach origin/main
git submodule status
```

Expected: `.gitmodules` contains only the two approved HTTPS URLs, and both
submodules show a clean detached commit without a leading `-`, `+`, or `U`.
Replace neither detached commit with unpublished local work.

- [ ] **Step 4: Implement strict lock parsing and source verification**

Use frozen Pydantic models with `extra="forbid"`. Accept only lowercase
40-character Git hashes, lowercase 64-character SHA-256 digests, the two exact
relative paths, and HTTPS URLs. Invoke Git with argument arrays and no shell:

```python
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess, run

from pydantic import BaseModel, ConfigDict, Field


class CompanionSourceError(RuntimeError):
    pass


class GitResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    returncode: int
    stdout: str
    stderr: str


class PackageLock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str
    source_url: str
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    package_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    contract_version: str = Field(pattern=r"^[0-9]+$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sbom_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_spdx: str = Field(pattern=r"^[A-Za-z0-9-.+]+$")


class CompanionLock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: int = Field(ge=1, le=1)
    promptx: PackageLock
    subagents: PackageLock


def run_git(path: Path, *arguments: str) -> GitResult:
    result: CompletedProcess[str] = run(
        ["git", "-C", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return GitResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def verify_sources(
    root: Path,
    lock: CompanionLock,
    *,
    git: Callable[..., GitResult] = run_git,
    require_present: bool = True,
) -> None:
    expected = {
        "promptx": ("packages/promptx", "https://github.com/GNour/promptx.git"),
        "subagents": ("packages/subagents", "https://github.com/GNour/subagents.git"),
    }
    for name, package in (("promptx", lock.promptx), ("subagents", lock.subagents)):
        if (package.path, package.source_url) != expected[name]:
            raise CompanionSourceError(f"{name} path or source URL mismatch")
        path = root / package.path
        if require_present and not path.is_dir():
            raise CompanionSourceError(f"missing companion source: {name}")
        head = git(path, "rev-parse", "HEAD")
        if head.returncode != 0 or head.stdout.strip() != package.source_commit:
            raise CompanionSourceError(f"{name} source commit mismatch")
        status = git(path, "status", "--porcelain", "--untracked-files=all")
        if status.returncode != 0 or status.stdout:
            raise CompanionSourceError(f"dirty companion source: {name}")
```

Generate `config/companions.lock.json` from the two checked-out commits and the
upstream version commands. Compute `artifact_sha256` from the reproducible
PromptX runtime tarball and the normalized Subagents catalog tarball, and compute
`sbom_sha256` from each generated SPDX SBOM; never type or copy a digest
manually.

- [ ] **Step 5: Verify and commit the admitted pins**

Run:

```bash
uv run pytest tests/unit/companions/test_lock.py tests/security/test_companion_source_state.py -q
git submodule foreach --recursive git status --short
git diff --check
```

Expected: tests pass, both recursive status outputs are empty, and the diff check
passes.

```bash
git add .gitmodules packages config/companions.lock.json src/aegis/companions tests
git commit -m "build(companions): pin admitted package sources"
```

### Task 2: Define strict Subagents input and Aegis role contracts

**Files:**
- Create: `config/companions/role-mappings.yaml`
- Create: `src/aegis/companions/subagents.py`
- Create: `tests/companions/fixtures/subagents-valid.json`
- Create: `tests/companions/fixtures/subagents-unknown-field.json`
- Create: `tests/companions/fixtures/subagents-duplicate-role.json`
- Create: `tests/unit/companions/test_subagents_contract.py`

- [ ] **Step 1: Write failing strict-contract tests**

```python
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.companions.subagents import SubagentsCatalog

FIXTURES = Path("tests/companions/fixtures")


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_catalog_preserves_advisory_fields_without_granting_authority() -> None:
    catalog = SubagentsCatalog.model_validate(load("subagents-valid.json"))
    assert catalog.catalog_schema_version == "1"
    assert catalog.roles[0].advisory_tools == ("Read", "Grep")


@pytest.mark.parametrize(
    "fixture",
    ["subagents-unknown-field.json", "subagents-duplicate-role.json"],
)
def test_malformed_catalog_fails_closed(fixture: str) -> None:
    with pytest.raises(ValidationError):
        SubagentsCatalog.model_validate(load(fixture))
```

The valid fixture must contain two departments, three roles, resolved advisory
handoffs, exact immutable skill provenance, and no executable field. The
malicious fixtures each change one property only.

- [ ] **Step 2: Confirm strict catalog models are missing**

Run:

```bash
uv run pytest tests/unit/companions/test_subagents_contract.py -q
```

Expected: FAIL during collection because `aegis.companions.subagents` does not
exist.

- [ ] **Step 3: Implement the complete input and output models**

Create frozen, strict models for `SkillProvenance`, `AdvisoryHandoff`,
`SubagentsRole`, `SubagentsDepartment`, `SubagentsCatalog`, `RoleMapping`,
`CompiledRole`, and `CompiledCatalog`. Enforce uniqueness and resolution in an
after-validator:

```python
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SkillProvenance(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    source: str
    version: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str = Field(min_length=1, max_length=128)


class AdvisoryHandoff(StrictModel):
    role_id: str
    reason: str = Field(min_length=1, max_length=500)
    required: bool


class SubagentsRole(StrictModel):
    id: str
    department_id: str
    name: str
    title: str
    description: str
    expertise: tuple[str, ...]
    invocation: str
    standards: tuple[str, ...]
    model_hint: str
    advisory_tools: tuple[str, ...]
    skills: tuple[SkillProvenance, ...]
    handoffs: tuple[AdvisoryHandoff, ...]


class SubagentsDepartment(StrictModel):
    id: str
    name: str


class SubagentsCatalog(StrictModel):
    package_version: str
    catalog_schema_version: str
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    departments: tuple[SubagentsDepartment, ...]
    roles: tuple[SubagentsRole, ...]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        department_ids = [item.id for item in self.departments]
        role_ids = [item.id for item in self.roles]
        if len(department_ids) != len(set(department_ids)):
            raise ValueError("duplicate department id")
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("duplicate role id")
        if any(role.department_id not in department_ids for role in self.roles):
            raise ValueError("unresolved department")
        if any(
            handoff.role_id not in role_ids
            for role in self.roles
            for handoff in role.handoffs
        ):
            raise ValueError("unresolved handoff")
        return self


class RoleMapping(StrictModel):
    model_alias: str
    capability_profile: str
    skills: tuple[str, ...]
    tools: tuple[str, ...]


class RoleMappings(StrictModel):
    schema_version: int = Field(ge=1, le=1)
    roles: dict[str, RoleMapping]


class CompiledRole(StrictModel):
    id: str
    department_id: str
    name: str
    title: str
    description: str
    expertise: tuple[str, ...]
    invocation: str
    standards: tuple[str, ...]
    model_alias: str
    capability_profile: str
    skills: tuple[SkillProvenance, ...]
    tools: tuple[str, ...]
    handoffs: tuple[AdvisoryHandoff, ...]


class CompiledCatalog(StrictModel):
    schema_version: int = Field(ge=1, le=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_package_version: str
    source_catalog_schema_version: str
    roles: tuple[CompiledRole, ...]
```

`CompiledRole` must omit `model_hint` and `advisory_tools`. It contains only the
reviewed `model_alias`, exact `skills`, generated typed-tool identifiers, and
`capability_profile`.

- [ ] **Step 4: Add explicit reviewed role mappings**

Create a strict YAML document with these initial mappings:

```yaml
schema_version: 1
roles:
  tech-lead:
    model_alias: planning
    capability_profile: read-only-planning
    skills: [systematic-debugging, writing-plans]
    tools: [qmd_search, qmd_get]
  python-dev:
    model_alias: implementation
    capability_profile: worktree-write
    skills: [backend-development, tdd]
    tools: [qmd_search, qmd_get, project_test]
  qa-engineer:
    model_alias: verification
    capability_profile: read-only-verification
    skills: [systematic-debugging, verification-before-completion]
    tools: [qmd_search, qmd_get, project_test]
```

The compiler must reject any upstream role, skill, tool string, or handoff that
is imported without an explicit reviewed mapping. Upstream tool strings are
never copied into this file automatically.

- [ ] **Step 5: Verify and commit the contracts**

Run:

```bash
uv run pytest tests/unit/companions/test_subagents_contract.py -q
uv run ruff check src/aegis/companions tests/unit/companions
uv run mypy src
```

Expected: all commands pass.

```bash
git add config/companions/role-mappings.yaml src/aegis/companions/subagents.py tests
git commit -m "feat(companions): define strict role catalog contracts"
```

### Task 3: Compile Subagents deterministically into release data

**Files:**
- Create: `src/aegis/companions/catalog.py`
- Create: `src/aegis/data/companions/roles.compiled.json`
- Create: `src/aegis/data/companions/roles.provenance.json`
- Create: `tools/companions.py`
- Create: `tests/unit/companions/test_catalog_compiler.py`
- Create: `tests/security/test_catalog_authority.py`

- [ ] **Step 1: Write failing determinism and authority tests**

```python
from aegis.companions.catalog import compile_catalog
from aegis.companions.subagents import RoleMappings, SubagentsCatalog


def test_compilation_is_deterministic(catalog: SubagentsCatalog, mappings: RoleMappings) -> None:
    first = compile_catalog(catalog, mappings)
    second = compile_catalog(
        SubagentsCatalog.model_validate_json(catalog.model_dump_json()),
        mappings,
    )
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256


def test_advisory_authority_is_absent(catalog: SubagentsCatalog, mappings: RoleMappings) -> None:
    result = compile_catalog(catalog, mappings)
    rendered = result.canonical_bytes.decode("utf-8")
    assert "advisory_tools" not in rendered
    assert "model_hint" not in rendered
    assert "Bash" not in rendered
    assert set(result.catalog.roles[0].tools) <= {"qmd_search", "qmd_get", "project_test"}
```

Add focused tests for unknown roles, unknown skills, unresolved handoffs,
mutable skill versions, missing checksums/licenses, cyclic required handoffs,
and changed input order.

- [ ] **Step 2: Confirm the compiler is missing**

Run:

```bash
uv run pytest tests/unit/companions/test_catalog_compiler.py tests/security/test_catalog_authority.py -q
```

Expected: FAIL during collection because `aegis.companions.catalog` does not
exist.

- [ ] **Step 3: Implement canonical compilation**

The compiler must be pure: no filesystem, subprocess, clock, environment, or
network access. Sort roles, skills, tools, and handoffs by stable identifier,
then hash compact UTF-8 JSON:

```python
from dataclasses import dataclass
from hashlib import sha256

from pydantic import TypeAdapter

from aegis.companions.subagents import CompiledCatalog, RoleMappings, SubagentsCatalog


@dataclass(frozen=True)
class CompilationResult:
    catalog: CompiledCatalog
    canonical_bytes: bytes
    sha256: str


def compile_catalog(
    source: SubagentsCatalog,
    mappings: RoleMappings,
) -> CompilationResult:
    source_by_id = {role.id: role for role in source.roles}
    if set(source_by_id) != set(mappings.roles):
        raise ValueError("every imported role requires exactly one reviewed mapping")
    compiled = CompiledCatalog.from_reviewed(source, mappings)
    adapter = TypeAdapter(CompiledCatalog)
    canonical = adapter.dump_json(compiled, by_alias=True, exclude_none=False)
    return CompilationResult(compiled, canonical, sha256(canonical).hexdigest())
```

`CompiledCatalog.from_reviewed` must look up each `RoleMapping`, confirm every
mapped skill exists in that role's immutable provenance, allow only the fixed
typed-tool registry `{qmd_search, qmd_get, project_test}`, validate every
handoff target, and construct each `CompiledRole` field explicitly. It must
never dump, merge, or spread an upstream dictionary into output.

- [ ] **Step 4: Generate and check committed assets**

Add an internal function that writes through a sibling temporary file, calls
`flush` and `os.fsync`, then uses `os.replace`. A `check=True` mode compares
bytes and fails without writing.

Run:

```bash
uv run python tools/companions.py compile-subagents
uv run python tools/companions.py compile-subagents --check
```

Expected: both commands exit `0`; the second reports that the compiled catalog
and provenance files match the accepted source and lock.

- [ ] **Step 5: Verify and commit deterministic catalog assets**

Run:

```bash
uv run pytest tests/unit/companions/test_catalog_compiler.py tests/security/test_catalog_authority.py -q
uv run python tools/companions.py compile-subagents --check
git diff --check
```

Expected: all checks pass.

```bash
git add src/aegis/companions/catalog.py src/aegis/data tests tools/companions.py
git commit -m "feat(companions): compile reviewed role catalog"
```

### Task 4: Add the bounded PromptX control-plane adapter

**Files:**
- Create: `src/aegis/companions/promptx.py`
- Create: `tests/companions/fixtures/promptx-success.json`
- Create: `tests/companions/fixtures/promptx-degraded.json`
- Create: `tests/companions/fixtures/promptx-unknown-field.json`
- Create: `tests/unit/companions/test_promptx_adapter.py`
- Create: `tests/security/test_promptx_boundary.py`

- [ ] **Step 1: Write failing contract, fallback, and boundary tests**

```python
from pathlib import Path

import pytest

from aegis.companions.promptx import (
    BrokerLease,
    PromptXAdapter,
    PromptXProtocolError,
    PromptXRequest,
    ProcessResult,
)


def request() -> PromptXRequest:
    return PromptXRequest.model_validate(
        {
            "schema_version": "1",
            "request_digest": "a" * 64,
            "prompt": "add bounded caching",
            "facts": [
                {"kind": "project-command", "value": "uv run pytest", "source_digest": "b" * 64}
            ],
            "allow_provider_refinement": True,
            "max_output_bytes": 8192,
        }
    )


def test_provider_failure_returns_valid_deterministic_result(tmp_path: Path) -> None:
    adapter = PromptXAdapter(
        executable=tmp_path / "promptx",
        expected_sha256="c" * 64,
        expected_package_version="1.0.0",
        expected_protocol_version="1",
        run_process=lambda *_args, **_kwargs: ProcessResult(
            returncode=0,
            stdout=Path("tests/companions/fixtures/promptx-degraded.json").read_bytes(),
            stderr=b"",
        ),
        digest_file=lambda _path: "c" * 64,
        audit=lambda _record: None,
    )
    result = adapter.enrich(
        request(),
        broker=BrokerLease(
            reference="broker:task:stage",
            token="opaque-token",
            url="http://127.0.0.1:4319/v1",
        ),
    )
    assert result.degraded is True
    assert result.deterministic_text


def test_unknown_output_field_fails_closed(tmp_path: Path) -> None:
    adapter = PromptXAdapter.for_fixture(
        tmp_path,
        Path("tests/companions/fixtures/promptx-unknown-field.json"),
    )
    with pytest.raises(PromptXProtocolError, match="invalid PromptX response"):
        adapter.enrich(request(), broker=None)
```

Security tests must also assert that the child environment excludes provider
keys and unrelated variables, the URL is exact loopback HTTP, redirects are
disabled by the upstream contract, branch/commit facts are bounded and redacted,
stderr/body content never enters an exception, and a secret canary is absent
from requests, results, diagnostics, and audit payloads. A fake audit sink must
receive one safe record for success, degraded fallback, timeout, and protocol
rejection.

- [ ] **Step 2: Confirm the adapter is missing**

Run:

```bash
uv run pytest tests/unit/companions/test_promptx_adapter.py tests/security/test_promptx_boundary.py -q
```

Expected: FAIL during collection because `aegis.companions.promptx` does not
exist.

- [ ] **Step 3: Implement strict request, response, and diagnostic models**

Use frozen strict Pydantic models and bound every string, tuple, and total
serialized response. The request accepts only sanitized facts with source
digests. The response contains deterministic text even when optional refinement
is degraded:

```python
class PromptXResponse(StrictModel):
    schema_version: str = Field(pattern=r"^1$")
    package_version: str
    protocol_version: str
    gate_verdict: str
    gate_reason: str = Field(max_length=256)
    task_class: str = Field(max_length=64)
    quality_score: float = Field(ge=0, le=1)
    deterministic_text: str = Field(min_length=1, max_length=8000)
    refined_text: str | None = Field(default=None, max_length=8000)
    fact_digests: tuple[str, ...] = Field(max_length=64)
    degraded: bool
    degradation_code: str | None = Field(default=None, max_length=64)
    duration_ms: int = Field(ge=0, le=120_000)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class PromptXAuditRecord(StrictModel):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fact_digests: tuple[str, ...] = Field(max_length=64)
    gate_verdict: str | None = Field(default=None, max_length=64)
    gate_reason: str | None = Field(default=None, max_length=256)
    task_class: str | None = Field(default=None, max_length=64)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    degraded: bool
    result_code: str = Field(max_length=64)
    duration_ms: int = Field(ge=0, le=120_000)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
```

Reject any authority-bearing output keys before model validation:
`flow`, `role`, `model`, `skills`, `tools`, `capabilities`, `approval`, and
`next_stage`.

- [ ] **Step 4: Implement the fixed subprocess boundary**

Invoke only the admitted executable with:

```python
command = [
    str(self.executable),
    "aegis-contract",
    "enrich",
    "--input-json",
    "-",
    "--disable-filesystem",
    "--disable-git",
]
```

Pass compact JSON on stdin, use a 15-second timeout, cap stdout and stderr before
decoding, and construct a fresh child environment containing only locale,
`PROMPTX_BROKER_URL`, and `PROMPTX_BROKER_TOKEN` when a valid broker lease is
present. The `BrokerLease.reference` is safe to persist; its token is never
serialized, logged, audited, or included in a stage packet. Verify the executable
digest and version response before the first enrichment and cache readiness only
for that adapter instance. Require a `Callable[[PromptXAuditRecord], None]` when
constructing the adapter and invoke it exactly once on every terminal outcome.
If recording fails, enrichment fails closed because dispatch without its audit
record is forbidden.

- [ ] **Step 5: Verify and commit the PromptX boundary**

Run:

```bash
uv run pytest tests/unit/companions/test_promptx_adapter.py tests/security/test_promptx_boundary.py -q
uv run ruff check src/aegis/companions tests/unit/companions tests/security
uv run mypy src
```

Expected: all commands pass.

```bash
git add src/aegis/companions/promptx.py tests/companions tests/unit/companions tests/security
git commit -m "feat(companions): add bounded PromptX adapter"
```

### Task 5: Define and canonically compile `StageExecutionPacket`

**Files:**
- Create: `src/aegis/domain/stage_packet.py`
- Create: `src/aegis/engine/__init__.py`
- Create: `src/aegis/engine/stage_packets.py`
- Modify: `src/aegis/domain/__init__.py`
- Create: `tests/unit/domain/test_stage_packet.py`
- Create: `tests/unit/engine/test_stage_packet_compiler.py`
- Create: `tests/security/test_stage_packet_authority.py`

- [ ] **Step 1: Write failing immutability and exact-version tests**

```python
import pytest

from pydantic import ValidationError

from aegis.domain.stage_packet import StagePacketInput
from aegis.engine.stage_packets import StagePacketCompiler


def test_packet_hash_is_stable_and_captures_exact_companions(
    packet_input: StagePacketInput,
) -> None:
    compiler = StagePacketCompiler()
    first = compiler.compile(packet_input)
    second = compiler.compile(packet_input)
    assert first.canonical_hash == second.canonical_hash
    assert first.promptx.source_commit == packet_input.promptx.source_commit
    assert first.subagents.catalog_sha256 == packet_input.subagents.catalog_sha256


def test_packet_rejects_unknown_or_authority_bearing_enrichment(
    packet_input_dict: dict[str, object],
) -> None:
    packet_input_dict["promptx_enrichment"] = {"text": "ok", "next_stage": "deploy"}
    with pytest.raises(ValidationError):
        StagePacketInput.model_validate(packet_input_dict)
```

Add tests for frozen nested mappings, non-finite numbers, budget bounds, source
digest mismatches, unauthorized tool/capability widening, missing evidence and
handoff requirements, canonical key ordering, and changed timestamps.

- [ ] **Step 2: Confirm packet modules are missing**

Run:

```bash
uv run pytest tests/unit/domain/test_stage_packet.py tests/unit/engine/test_stage_packet_compiler.py tests/security/test_stage_packet_authority.py -q
```

Expected: FAIL during collection because `aegis.domain.stage_packet` and
`aegis.engine.stage_packets` do not exist.

- [ ] **Step 3: Implement immutable packet contracts**

Reuse `DomainRecord`, `FrozenJsonMapping`, `CatalogIdentifier`,
`NonNegativeFloat`, `NonNegativeInt`, `PositiveInt`, `UUID7`, and `UtcDatetime`.
Define explicit models for companion identities and a packet input whose fields
cannot include raw credentials:

```python
class PromptXIdentity(DomainRecord):
    source_commit: str
    package_version: str
    protocol_version: str
    executable_sha256: str
    configuration_sha256: str


class SubagentsIdentity(DomainRecord):
    source_commit: str
    package_version: str
    catalog_schema_version: str
    catalog_sha256: str
    provenance_sha256: str


class PromptXEnrichmentSnapshot(DomainRecord):
    gate_verdict: CatalogIdentifier
    gate_reason: str
    task_class: CatalogIdentifier
    quality_score: float = Field(ge=0, le=1)
    deterministic_text: str
    refined_text: str | None
    fact_digests: tuple[str, ...]
    degraded: bool
    degradation_code: str | None
    duration_ms: NonNegativeInt
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt


class StagePacketBody(DomainRecord):
    schema_version: PositiveInt
    task_id: UUID7
    flow_run_id: UUID7
    stage_run_id: UUID7
    attempt_ordinal: NonNegativeInt
    task_snapshot: FrozenJsonMapping
    flow_snapshot: FrozenJsonMapping
    stage_snapshot: FrozenJsonMapping
    role_snapshot: FrozenJsonMapping
    model_snapshot: FrozenJsonMapping
    skill_snapshots: tuple[FrozenJsonMapping, ...]
    capability_snapshot: FrozenJsonMapping
    project_snapshot: FrozenJsonMapping
    request_digest: str
    promptx_enrichment: PromptXEnrichmentSnapshot
    context_snapshot: FrozenJsonMapping
    tool_definitions: tuple[FrozenJsonMapping, ...]
    broker_capability_reference: str | None
    budgets: FrozenJsonMapping
    completion_requirements: FrozenJsonMapping
    artifact_requirements: tuple[FrozenJsonMapping, ...]
    decision_requirements: tuple[FrozenJsonMapping, ...]
    approval_requirements: tuple[FrozenJsonMapping, ...]
    handoff_requirements: FrozenJsonMapping
    promptx: PromptXIdentity
    subagents: SubagentsIdentity


class StagePacketInput(StagePacketBody):
    id: UUID7
    created_at: UtcDatetime

    def packet_values(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class StageExecutionPacket(StagePacketInput):
    canonical_hash: str
```

The serialized packet must never contain a broker token, provider key, raw
credential, upstream advisory tool field, or repository path.

- [ ] **Step 4: Implement the only packet compiler**

Model `StagePacketBody` with all snapshot and requirement fields,
`StagePacketInput` as the body plus `id` and `created_at`, and
`StageExecutionPacket` as the input plus `canonical_hash`. This makes
`StagePacketInput.packet_values()` a complete `model_dump(mode="json")` without
duplicating field names. The explicit `PromptXEnrichmentSnapshot` makes
authority-bearing keys fail validation instead of hiding in a generic mapping.

`StagePacketCompiler.compile` accepts one validated `StagePacketInput`, renders
the packet with `canonical_hash=""`, produces compact sorted UTF-8 JSON, hashes
those bytes with SHA-256, and returns a new validated packet containing the hash.
It performs no I/O and reads no global configuration:

```python
import hashlib
import json


class StagePacketCompiler:
    def compile(self, source: StagePacketInput) -> StageExecutionPacket:
        values = source.packet_values()
        unsigned = StageExecutionPacket.model_validate(
            {**values, "canonical_hash": "0" * 64}
        )
        payload = unsigned.model_dump(mode="json")
        payload["canonical_hash"] = ""
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        return StageExecutionPacket.model_validate(
            {**unsigned.model_dump(mode="json"), "canonical_hash": digest}
        )
```

- [ ] **Step 5: Verify and commit packet compilation**

Run:

```bash
uv run pytest tests/unit/domain/test_stage_packet.py tests/unit/engine/test_stage_packet_compiler.py tests/security/test_stage_packet_authority.py -q
uv run mypy src
```

Expected: all commands pass.

```bash
git add src/aegis/domain src/aegis/engine tests/unit/domain tests/unit/engine tests/security
git commit -m "feat(engine): compile immutable stage packets"
```

### Task 6: Persist packets exactly once before dispatch

**Files:**
- Create: `src/aegis/storage/schema/0003_stage_execution_packets.sql`
- Modify: `src/aegis/storage/sqlite.py`
- Create: `tests/unit/storage/test_stage_packets.py`
- Create: `tests/recovery/test_stage_packet_restart.py`

- [ ] **Step 1: Write failing persistence and restart tests**

```python
import pytest

from aegis.storage.sqlite import SQLiteStore


def test_store_inserts_one_exact_packet(store: SQLiteStore, packet) -> None:
    store.save_stage_packet(packet)
    loaded = store.get_stage_packet(packet.stage_run_id)
    assert loaded == packet
    store.save_stage_packet(packet)
    assert store.get_stage_packet(packet.stage_run_id) == packet


def test_changed_packet_for_same_stage_is_rejected(store: SQLiteStore, packet) -> None:
    store.save_stage_packet(packet)
    changed = packet.model_copy(update={"canonical_hash": "f" * 64})
    with pytest.raises(ValueError, match="stage packet conflict"):
        store.save_stage_packet(changed)


def test_restart_reuses_persisted_packet(tmp_path, packet) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path) as first:
        first.save_stage_packet(packet)
    with SQLiteStore(path) as restarted:
        assert restarted.get_stage_packet(packet.stage_run_id) == packet
```

Also test a tampered JSON body, mismatched stored hash, a missing stage foreign
key, concurrent identical inserts, concurrent conflicting inserts, startup
reload, and the native-resume seam returning the stored packet without invoking
`StagePacketCompiler` again.

- [ ] **Step 2: Confirm storage has no packet table or API**

Run:

```bash
uv run pytest tests/unit/storage/test_stage_packets.py tests/recovery/test_stage_packet_restart.py -q
```

Expected: FAIL because migration `0003_stage_execution_packets.sql` and the
store methods do not exist.

- [ ] **Step 3: Add the one-packet-per-stage migration**

```sql
CREATE TABLE stage_execution_packets (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    flow_run_id TEXT NOT NULL REFERENCES flow_runs(id),
    stage_run_id TEXT NOT NULL UNIQUE REFERENCES stage_runs(id),
    schema_version INTEGER NOT NULL,
    packet_json TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_stage_execution_packets_task_id
    ON stage_execution_packets(task_id);
CREATE INDEX idx_stage_execution_packets_flow_run_id
    ON stage_execution_packets(flow_run_id);
```

Extend the existing exact schema dictionaries in `sqlite.py`; do not enable
schema-extension bypasses in production tests.

- [ ] **Step 4: Implement insert-once and integrity-checked reads**

`save_stage_packet` must start `BEGIN IMMEDIATE`, compare an existing row before
returning idempotently, insert compact canonical JSON otherwise, read the row
back, validate it as `StageExecutionPacket`, recompute its canonical hash, and
commit only after all comparisons pass. Any exception rolls back. A conflicting
packet for the same `stage_run_id` raises `ValueError("stage packet conflict")`.

`get_stage_packet` must validate UUIDv7 input, reject malformed JSON or unknown
fields, recompute the canonical hash, and return `None` only when no row exists.
`get_stage_packet_for_resume` delegates to that integrity-checked read and never
accepts snapshots or a compiler, making recompilation during restart or native
resume structurally unavailable.

- [ ] **Step 5: Verify and commit durable packet storage**

Run:

```bash
uv run pytest tests/unit/storage tests/recovery/test_stage_packet_restart.py -q
uv run mypy src
```

Expected: all storage and restart tests pass.

```bash
git add src/aegis/storage tests/unit/storage tests/recovery
git commit -m "feat(storage): persist exact stage packets"
```

### Task 7: Add companion build, readiness, and packaging gates

**Files:**
- Modify: `tools/companions.py`
- Modify: `src/aegis/cli.py`
- Modify: `pyproject.toml`
- Create: `tests/integration/test_companion_build.py`
- Create: `tests/integration/test_companion_readiness.py`
- Create: `tests/security/test_runtime_package_contents.py`

- [ ] **Step 1: Write failing clean-build and image-content tests**

```python
import json
import zipfile


def test_wheel_contains_compiled_catalog_but_not_subagents_source(built_wheel) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
    assert "aegis/data/companions/roles.compiled.json" in names
    assert "aegis/data/companions/roles.provenance.json" in names
    assert all("packages/subagents" not in name for name in names)
    assert all("install.sh" not in name for name in names)


def test_readiness_rejects_promptx_digest_mismatch(cli_runner) -> None:
    result = cli_runner.invoke(["companions", "verify"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["code"] == "promptx_artifact_mismatch"
```

Add clean recursive-clone, missing submodule, dirty submodule, incompatible
protocol/schema, nondeterministic output, missing license, advanced pin, worker
image absence, and coordinated rollback fixtures.

- [ ] **Step 2: Confirm build and readiness commands are absent**

Run:

```bash
uv run pytest tests/integration/test_companion_build.py tests/integration/test_companion_readiness.py tests/security/test_runtime_package_contents.py -q
```

Expected: FAIL because the build helper, CLI group, and package-data declaration
do not exist.

- [ ] **Step 3: Implement one build/check entry point**

`tools/companions.py` must expose these fixed subcommands:

```text
verify-sources
build-promptx
compile-subagents
evaluate
check
```

`check` runs source verification, upstream version negotiation, PromptX
reproducible build/digest verification, Subagents validation and deterministic
compilation, committed-asset comparison, license/provenance validation, and
package-content assertions. `evaluate` runs PromptX's offline characteristic
suite and compiles one packet-input fixture for every imported role, proving
each mapping resolves without inventing authority. Both return structured JSON
and never accept an arbitrary executable or command argument.

- [ ] **Step 4: Embed only approved release assets**

Add explicit package-data entries:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/aegis"]

[tool.hatch.build.targets.wheel.force-include]
"src/aegis/data/companions/roles.compiled.json" = "aegis/data/companions/roles.compiled.json"
"src/aegis/data/companions/roles.provenance.json" = "aegis/data/companions/roles.provenance.json"
```

The control-plane container build later copies the verified PromptX runtime
artifact and lock. Worker-image contexts must exclude `packages/`,
`src/aegis/companions/`, the compiled global catalog, and all broker material.

- [ ] **Step 5: Add the bounded readiness CLI and commit**

Add a `companions verify` Typer command that emits only:

```json
{"ready":true,"code":"ready","promptx_package_version":"1.0.0","promptx_protocol_version":"1","subagents_package_version":"1.0.0","subagents_catalog_schema_version":"1"}
```

Failure output contains stable codes and safe version/digest names, never paths,
subprocess bodies, environment values, prompts, facts, or credentials.

Run:

```bash
uv run python tools/companions.py check
uv run python tools/companions.py evaluate
uv build
uv run pytest tests/integration/test_companion_build.py tests/integration/test_companion_readiness.py tests/security/test_runtime_package_contents.py -q
```

Expected: all commands pass.

```bash
git add tools/companions.py src/aegis/cli.py pyproject.toml tests/integration tests/security
git commit -m "build(companions): enforce release readiness"
```

### Task 8: Prove upgrade, rollback, security, and requirement coverage

**Files:**
- Create: `tests/recovery/test_companion_upgrade_rollback.py`
- Create: `tests/security/test_companion_prompt_injection.py`
- Create: `tests/security/test_companion_environment.py`
- Modify: `docs/specs/08-verification-matrix.md`
- Modify: `docs/specs/09-traceability.md`
- Modify: `docs/plans/00-implementation-roadmap.md`
- Modify: `README.md`

- [ ] **Step 1: Write the failing coordinated rollback test**

```python
def test_rollback_restores_one_compatible_companion_set(release_fixture) -> None:
    previous = release_fixture.install("previous")
    current = release_fixture.install("current")
    assert current.readiness().ready is True

    restored = release_fixture.rollback(to=previous.release_digest)

    assert restored.promptx_digest == previous.promptx_digest
    assert restored.catalog_digest == previous.catalog_digest
    assert restored.lock_digest == previous.lock_digest
    assert restored.configuration_digest == previous.configuration_digest
    assert restored.readiness().ready is True
```

Add a negative case proving that mixing the previous PromptX artifact with the
current catalog/lock fails readiness before dispatch.

- [ ] **Step 2: Add the complete adversarial corpus**

Cover prompt injection in role text, skill metadata, Git branch and commit
subjects, injected facts, and PromptX output; symlink/path escape; endpoint
redirection; environment leakage; oversized/nested JSON; non-finite numbers;
duplicate keys; invalid UTF-8; malicious catalog authority fields; missing or
mutable provenance; and submodule state changes during a build.

Run:

```bash
uv run pytest tests/security/test_companion_prompt_injection.py tests/security/test_companion_environment.py -q
```

Expected: every adversarial case is rejected with a stable safe error, and the
secret canary is absent from captured output.

- [ ] **Step 3: Make the full integration gate pass**

Run:

```bash
uv run python tools/companions.py check
uv run python tools/companions.py evaluate
uv run ruff check .
uv run mypy src
uv run pytest
uv run pytest tests/security tests/recovery
git submodule foreach --recursive git status --short
git diff --check
```

Expected: every command exits `0`, all recursive submodule status output is
empty, and the security/recovery suites include companion integration coverage.

- [ ] **Step 4: Update traceability and operational status**

Map FR-046 through FR-049 and NFR-009 to Tasks 1–8 and their exact test paths.
Mark this plan implemented only after Step 3 passes on the current commit.
Document the pinned commits and artifact digests by reference to
`config/companions.lock.json`; do not duplicate mutable values in prose.

- [ ] **Step 5: Commit the completed integration**

```bash
git add README.md docs tests/security tests/recovery
git commit -m "test(companions): gate upgrade and rollback"
```

## Completion gate

This plan is complete only when:

1. the two HTTPS submodules and lock point to accepted, clean upstream commits;
2. a clean recursive clone reproduces the PromptX and compiled Subagents assets;
3. PromptX readiness and every enrichment validate exact versions and digests;
4. the compiled role catalog contains only reviewed Aegis authority;
5. every packet is canonical, stored once, and reloaded unchanged after restart;
6. no worker or runtime artifact contains prohibited companion source, installer,
   global catalog, provider credential, or broker token;
7. missing, dirty, advanced, incompatible, malicious, and mixed-version inputs
   fail closed; and
8. the full Ruff, mypy, pytest, security, recovery, package, and documentation
   checks pass on the final commit.

## Requirement coverage

| Requirement | Plan evidence |
|---|---|
| FR-046 immutable packet before dispatch | Tasks 5–6; domain, compiler, storage, restart, and native-resume tests |
| FR-047 pinned reproducible companions | Tasks 1, 3, 7, and 8; source-state, clean-build, provenance, upgrade, and rollback tests |
| FR-048 typed broker-only PromptX | Tasks 4, 5, 7, and 8; contract, audit, redaction, environment, endpoint, and packet tests |
| FR-049 build-time authority-free Subagents | Tasks 2–3, 5, 7, and 8; schema, mapping, deterministic compilation, package-content, and malicious-catalog tests |
| NFR-009 companion maintainability | Entry gate and Tasks 1, 3, 7, and 8; upstream-first workflow, lock/SBOM digests, compatibility, clean clone, and coordinated rollback |
