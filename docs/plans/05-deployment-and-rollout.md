# Container-First Deployment Implementation Plan

Status: implemented — all eight tasks complete, written from the accepted
[container-first deployment design](../superpowers/specs/2026-07-23-container-first-deployment-design.md)
and replacing the superseded Ansible-first plan. The product-metadata source of truth,
versioned appliance config with secret separation, private Compose bundle, container
runtime port + management surface, signed releases with digest-pinned updates and
automatic rollback, portable backup/verify/restore, idempotent installer + doctor/repair
+ scoped uninstall, and the `ae appliance` CLI (+ docs and install.sh wrapper) all pass
(`uv run ruff check .`, `uv run pytest`, `uv run mypy src/aegis` clean except the
pre-existing Windows-only `audit/ledger.py` msvcrt errors). Live rootless-Docker/VPS and
multi-arch CI are built against typed ports with fakes and gated behind `AEGIS_LIVE_*`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Aegis as a rootless Docker Compose appliance an operator installs,
configures, runs, inspects, upgrades, backs up, restores, and removes through one
management command — with the design's security and state invariants enforced and
tested.

**Architecture:** A single product-metadata file is the source of truth for names,
paths, labels, and namespaces. A versioned, schema-validated appliance configuration
renders a private-network Compose bundle. All container operations go through a typed
`ContainerRuntime` port (argument arrays, exact Compose project, never a global prune)
with a deterministic fake for tests and a rootless-Docker adapter for production. Update,
backup/restore, doctor/repair, install, and uninstall are orchestrated in Python against
typed host/runtime/registry ports; the host `install.sh` and CI multi-arch/live-VPS
matrix are thin wrappers over the same contracts and run only in a real environment.

**Environment reality (adaptation):** This build environment has no rootless Docker
daemon, registry, or VPS. Following the roadmap's port/fake convention (as used for
Herdr/QMD/OpenViking in plans 2–3), every subsystem is built against a typed port with
deterministic fakes and full unit/security coverage; live tests are marked and skipped
unless the corresponding environment (`AEGIS_LIVE_DOCKER`, `AEGIS_LIVE_VPS`) is present.
The appliance management surface lives under the `ae appliance …` command group to
coexist with the existing control-plane `ae config`/`ae flow` groups; a unified
top-level surface and the published `install.sh`/CI matrix are release-time packaging.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, tarfile, hashlib/hmac, rootless
Docker + Compose (adapter only), pytest.

---

### Task 1: Product metadata single source of truth

**Files:**
- Create: `config/product.toml`
- Create: `src/aegis/deploy/product.py`
- Create: `tests/unit/deploy/test_product.py`

Define one versioned product-metadata record (display name, CLI command, package name,
image registry namespace, Compose project name, config/data/backup directories, service
labels, documentation variables). Installers, Compose templates, and docs derive from it.
Persistent internal identifiers stay stable across a rename; a renamed CLI ships a
deprecation alias for a documented window.

- [ ] Write tests: metadata loads from the committed file; derived values (compose
  project, image ref for a service+digest, label set, directories) are deterministic; a
  rename preserves stable internal identifiers and yields a legacy alias.
- [ ] Confirm failure, implement `ProductMetadata`, confirm green, commit
  `feat(deploy): define product metadata source of truth`.

### Task 2: Versioned appliance configuration and secret separation

**Files:**
- Create: `src/aegis/deploy/config.py`
- Create: `config/schemas/appliance-v1.json`
- Create: `tests/unit/deploy/test_appliance_config.py`
- Create: `tests/security/test_config_secret_separation.py`

A versioned, `extra="forbid"` `ApplianceConfig` (channel, network exposure, service
toggles, resource limits, secret **references** — never secret values). Support
`init`/`validate`/`diff`, a stable nonsecret digest, and environment overrides as inputs
only. Secrets live in a separate least-readable store; a validator rejects inline secret
values and any public port on the private services.

- [ ] Write tests: dangerous configs (inline secret, public bind of a private service,
  unknown key, unsupported version) are rejected; the sanitized config validates; the
  nonsecret digest is stable and excludes secret references' values; diff reports changes;
  the committed JSON schema matches the generated one.
- [ ] Implement, confirm green, commit `feat(deploy): validate appliance configuration`.

### Task 3: Private-network Compose bundle rendering

**Files:**
- Create: `src/aegis/deploy/compose.py`
- Create: `tests/security/test_compose_bundle.py`

Render the Compose project from product metadata + config: Aegis/Herdr/QMD/OpenViking on
private networks with **no** published public ports; loopback/Unix endpoints only where a
host boundary is required; the two-account trust boundary (`agentops`/`hermesops`); the
control-plane adapter is the only service granted the rootless runtime API — worker,
gateway, and knowledge containers never receive a Docker socket; every service carries the
product labels; images pinned by immutable digest.

- [ ] Write security tests: no service publishes a public port; no worker/gateway/knowledge
  service mounts a Docker socket; no privileged/host-network/device/host-path options;
  every image is digest-pinned; labels present; gateway can reach only the control socket.
- [ ] Implement, confirm green, commit `feat(deploy): render private compose bundle`.

### Task 4: Container runtime port and management surface

**Files:**
- Create: `src/aegis/deploy/runtime.py`
- Create: `src/aegis/deploy/manager.py`
- Create: `tests/unit/deploy/test_manager.py`
- Create: `tests/security/test_runtime_scope.py`

A typed `ContainerRuntime` (up/down/ps/logs/exec/restart/inspect) built on argument arrays
against the exact Compose project — never a global prune, never unlabeled resources — with
a `FakeContainerRuntime` and a rootless-Docker adapter. The manager exposes
status/ps/logs/shell/exec/inspect/restart with authorization tiers (read-only delegable;
shell/exec/config/secret/update/backup/restore/destructive require elevated authorization
and emit audit events).

- [ ] Write tests: read-only ops need only operator group; privileged ops require elevated
  authorization and produce audit events; teardown targets the exact project and never
  prunes; unknown service is rejected.
- [ ] Implement, confirm green, commit `feat(deploy): manage appliance containers`.

### Task 5: Signed releases, digest-pinned updates, and automatic rollback

**Files:**
- Create: `src/aegis/deploy/release.py`
- Create: `src/aegis/deploy/update.py`
- Create: `tests/unit/deploy/test_release.py`
- Create: `tests/unit/deploy/test_update.py`

A signed release manifest (channel, version, per-service image digests, migration and
rollback metadata, doc/notes/SBOM references). `verify` rejects a bad signature, a mutable
`latest` tag, or a missing digest. The publication gate refuses when docs, release notes,
migrations, rollback metadata, signatures, or release-required tests are absent. The update
orchestrator: verify manifest → compatibility checks → pre-upgrade backup → pull by digest
→ validate candidate Compose → replace in dependency order → migrate + readiness → record
installed manifest → auto-rollback when the manifest declares rollback safe and readiness
fails.

- [ ] Write tests: bad signature/`latest`/missing digest rejected; publication gate blocks
  incomplete releases; a failed readiness check triggers automatic rollback to the prior
  manifest; a success records the new manifest; downgrade blocked unless allowed.
- [ ] Implement, confirm green, commit
  `feat(deploy): verify signed releases and roll back failed updates`.

### Task 6: Portable backup, verify, and restore

**Files:**
- Create: `src/aegis/deploy/backup.py`
- Create: `tests/unit/deploy/test_backup.py`
- Create: `tests/security/test_backup_contents.py`

Backups include operational state, audit segments, config/flow snapshots, Herdr metadata,
canonical knowledge, required artifacts, sanitized archives, and non-rebuildable OpenViking
state; they exclude rebuildable QMD indexes, images, worktrees, and disposable services.
Secret backup requires an explicitly configured encrypted destination. `create` produces a
portable archive + manifest; `verify` checks integrity; `restore` rehydrates onto a clean
host.

- [ ] Write tests: excluded classes never appear; included classes round-trip;
  create→verify→restore reproduces state on a fresh dir; secret backup without an encrypted
  destination is refused; a tampered archive fails verify.
- [ ] Implement, confirm green, commit `feat(deploy): portable backup and restore`.

### Task 7: Installer preflight, idempotent reconcile, doctor/repair, uninstall

**Files:**
- Create: `src/aegis/deploy/installer.py`
- Create: `src/aegis/deploy/doctor.py`
- Create: `src/aegis/deploy/uninstall.py`
- Create: `tests/unit/deploy/test_installer.py`
- Create: `tests/unit/deploy/test_doctor.py`
- Create: `tests/security/test_uninstall_scope.py`

Preflight verifies distro/release/arch/kernel/storage/network and its own release metadata
before changes. Reconcile is idempotent: it adopts existing identities/directories/services
without duplication. `doctor` checks rootless Docker, user namespaces, disk, permissions,
config, images, networking, volumes, sockets, readiness, and DB integrity; `repair` performs
only bounded, documented remediations and reports each. Uninstall removes only labeled
appliance resources, preserves durable data by default, and requires resolved-path
validation + explicit confirmation for `--purge-data`; no lifecycle command runs a global
prune.

- [ ] Write tests: preflight fails closed on an unsupported host; a second install is
  idempotent (no duplicates); doctor classifies a broken environment and repair reports
  bounded fixes; uninstall preserves data by default; `--purge-data` requires confirmation
  and validated paths; no command touches unrelated resources.
- [ ] Implement, confirm green, commit
  `feat(deploy): idempotent install, doctor, and scoped uninstall`.

### Task 8: `ae appliance` CLI, release docs, and live-gated integration

**Files:**
- Modify: `src/aegis/cli.py`
- Create: `deploy/install.sh`
- Create: `docs/deployment/README.md`
- Create: `tests/integration/deploy/test_cli_surface.py`
- Create: `tests/integration/deploy/test_live_appliance.py`

Wire the `ae appliance` command group (status/ps/logs/shell/exec/inspect/restart, config
init/validate/diff/apply, update/rollback/version, doctor/repair, backup create/verify,
restore, support-bundle, uninstall) over the Python orchestrators with a fake runtime for
tests. Add the host `install.sh` wrapper (checksum/signature inspection + local-exec
alternative) and deployment docs. Add live integration tests skipped unless
`AEGIS_LIVE_DOCKER`/`AEGIS_LIVE_VPS` are set.

- [ ] Write tests: the CLI surface exposes every documented command against the fake
  runtime; live tests are collected-but-skipped without the env; docs links/commands exist.
- [ ] Implement, confirm green, commit
  `feat(deploy): appliance management cli and release docs`.

---

## Release-required verification (design §9)

The design's release matrix (clean 22.04/24.04 install, interactive/unattended,
interrupted/idempotent install, runtime/account/socket/network/mount/secret boundaries,
config apply/rollback, operator authorization, stable/edge/pinned updates, interrupted
downloads/upgrades, migrations, auto-rollback, backup/verify/clean-host restore/cross-host
migration, reboot recovery, rename/alias, uninstall preserve/purge, untouched unrelated
resources, no public listeners, valid docs) is encoded as: (a) unit/security tests against
fakes that run in the normal gate, and (b) `AEGIS_LIVE_*`-gated integration tests that run
on a provisioned host. Multi-architecture publication marks an architecture unsupported
rather than shipping an unverified image.
