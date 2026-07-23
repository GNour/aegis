# Deployment and Rollout Implementation Plan

Status: superseded pending container-first rewrite

> **Do not execute this plan.** The accepted
> [container-first deployment design](../superpowers/specs/2026-07-23-container-first-deployment-design.md)
> replaces its Ansible-first delivery model. A new implementation plan will be
> written after the accepted design has completed its documentation review gate.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Aegis reproducibly on Ubuntu 24.04 with isolated service accounts, hardened services, private exposure, encrypted backups, recovery drills, and measured pilot gates.

**Architecture:** A reusable Ansible collection in this repository owns Aegis-specific accounts, packages, configuration, systemd, rootless runtime, and backup hooks. The VPS repo imports a pinned release and instance variables. Molecule proves convergence and security properties before a staged VPS rollout.

**Tech Stack:** Ansible, Molecule with Docker, systemd user/system units, rootless Docker, restic hooks, pytest security/recovery suites, GitHub Actions

---

### Task 1: Reusable Ansible aegis role and Molecule scenario

**Files:**
- Create: `deploy/ansible/requirements.yml`
- Create: `deploy/ansible/Makefile`
- Create: `deploy/ansible/roles/aegis/defaults/main.yml`
- Create: `deploy/ansible/roles/aegis/tasks/main.yml`
- Create: `deploy/ansible/molecule/default/molecule.yml`
- Create: `deploy/ansible/molecule/default/converge.yml`
- Create: `deploy/ansible/molecule/default/verify.yml`

- [ ] **Step 1: Write Molecule account assertions before role tasks**

```yaml
- name: Verify aegis accounts
  hosts: all
  gather_facts: false
  tasks:
    - ansible.builtin.getent:
        database: passwd
        key: "{{ item }}"
      loop:
        - hermesops
        - agentops
    - ansible.builtin.command: "id -nG {{ item }}"
      loop:
        - hermesops
        - agentops
      register: aegis_groups
      changed_when: false
    - ansible.builtin.assert:
        that:
          - "'sudo' not in item.stdout.split()"
          - "'docker' not in item.stdout.split()"
      loop: "{{ aegis_groups.results }}"
```

- [ ] **Step 2: Run Molecule and confirm role absence**

Run: `cd deploy/ansible && make molecule`

Expected: FAIL because the role/defaults do not exist.

- [ ] **Step 3: Add variables and idempotent account/directories tasks**

```yaml
# roles/aegis/defaults/main.yml
aegis_gateway_user: hermesops
aegis_orchestrator_user: agentops
aegis_operator_group: aegis-operators
aegis_version: "0.5.0-pilot"
aegis_state_dir: /var/lib/aegis
aegis_worktree_dir: /var/lib/aegis-worktrees
aegis_artifact_dir: /var/lib/aegis-artifacts
aegis_runtime_dir: /run/aegis
aegis_openviking_bind: 127.0.0.1
aegis_openviking_port: 1933
aegis_worker_concurrency: 2
```

```yaml
# roles/aegis/tasks/main.yml
- name: Create Aegis operator group
  ansible.builtin.group:
    name: "{{ aegis_operator_group }}"
    system: true

- name: Create locked Aegis service accounts
  ansible.builtin.user:
    name: "{{ item.name }}"
    system: true
    create_home: true
    password_lock: true
    shell: /usr/sbin/nologin
    groups: "{{ item.groups }}"
    append: false
  loop:
    - { name: "{{ aegis_gateway_user }}", groups: "{{ aegis_operator_group }}" }
    - { name: "{{ aegis_orchestrator_user }}", groups: "" }

- name: Create private Aegis directories
  ansible.builtin.file:
    path: "{{ item.path }}"
    state: directory
    owner: "{{ aegis_orchestrator_user }}"
    group: "{{ aegis_orchestrator_user }}"
    mode: "{{ item.mode }}"
  loop:
    - { path: "{{ aegis_state_dir }}", mode: "0700" }
    - { path: "{{ aegis_worktree_dir }}", mode: "0700" }
    - { path: "{{ aegis_artifact_dir }}", mode: "0700" }
```

- [ ] **Step 4: Run lint, converge, and idempotency**

Run: `cd deploy/ansible && make lint && make molecule`

Expected: lint exits 0; Molecule's second convergence reports zero changes and account assertions pass.

- [ ] **Step 5: Commit the deployment role skeleton**

```bash
git add deploy/ansible
git commit -m "feat(deploy): provision isolated aegis accounts"
```

### Task 2: Pinned installation and hardened systemd services

**Files:**
- Create: `deploy/ansible/roles/aegis/tasks/install.yml`
- Create: `deploy/ansible/roles/aegis/tasks/services.yml`
- Create: `deploy/ansible/roles/aegis/templates/aegis.service.j2`
- Create: `deploy/ansible/roles/aegis/templates/herdr.service.j2`
- Create: `deploy/ansible/roles/aegis/templates/hermes-ops.service.j2`
- Create: `deploy/ansible/roles/aegis/templates/openviking.service.j2`

- [ ] **Step 1: Add service-hardening assertions to Molecule**

```yaml
- name: Read Aegis unit security score
  ansible.builtin.command: systemd-analyze security aegis.service --no-pager
  register: aegis_security
  changed_when: false
- ansible.builtin.assert:
    that:
      - "'NoNewPrivileges=yes' in aegis_security.stdout"
      - "'ProtectSystem=strict' in aegis_security.stdout"
```

- [ ] **Step 2: Run Molecule and confirm units are missing**

Run: `cd deploy/ansible && make molecule`

Expected: FAIL because `aegis.service` is not installed.

- [ ] **Step 3: Install checksum-pinned artifacts and units**

```ini
# templates/aegis.service.j2
[Unit]
Description=Aegis agent control plane
After=network-online.target
Wants=network-online.target

[Service]
User={{ aegis_orchestrator_user }}
Group={{ aegis_orchestrator_user }}
UMask=0077
ExecStart=/opt/aegis/{{ aegis_version }}/bin/aegis serve --socket {{ aegis_runtime_dir }}/control.sock
Restart=on-failure
RestartSec=10s
StartLimitIntervalSec=300
StartLimitBurst=5
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={{ aegis_state_dir }} {{ aegis_worktree_dir }} {{ aegis_artifact_dir }} {{ aegis_runtime_dir }}
RestrictSUIDSGID=yes
LockPersonality=yes

[Install]
WantedBy=multi-user.target
```

Download the immutable Aegis artifact to a versioned path, verify
`aegis_release_sha256`, install its locked environment, and atomically update
`/opt/aegis/current`. Preflight `hermes gateway start --help` and render only
supported flags; the unit must not include `--foreground` unless the installed
version documents it.

- [ ] **Step 4: Run service and restart-loop tests**

Run: `cd deploy/ansible && make molecule`

Expected: all units become active, use intended users, pass readiness, stay below the restart-burst threshold, and meet hardening assertions.

- [ ] **Step 5: Commit services**

```bash
git add deploy/ansible/roles/aegis deploy/ansible/molecule
git commit -m "feat(deploy): install pinned hardened aegis services"
```

### Task 3: Rootless runtime, sockets, and exposure assertions

**Files:**
- Create: `deploy/ansible/roles/aegis/tasks/rootless.yml`
- Create: `deploy/ansible/roles/aegis/tasks/sockets.yml`
- Create: `deploy/ansible/molecule/default/verify_exposure.yml`

- [ ] **Step 1: Write negative socket/listener checks**

```yaml
- name: Capture listening sockets
  ansible.builtin.command: ss -lntup
  register: sockets
  changed_when: false
- ansible.builtin.assert:
    that:
      - "'0.0.0.0:1933' not in sockets.stdout"
      - "'[::]:1933' not in sockets.stdout"
      - "'0.0.0.0:8181' not in sockets.stdout"
      - "'[::]:8181' not in sockets.stdout"

- name: Confirm gateway cannot read Herdr socket
  ansible.builtin.command: "sudo -u {{ aegis_gateway_user }} test ! -r {{ aegis_runtime_dir }}/herdr.sock"
  changed_when: false
```

- [ ] **Step 2: Run checks and observe missing runtime/socket configuration**

Run: `cd deploy/ansible && make molecule`

Expected: FAIL before rootless runtime and socket permissions converge.

- [ ] **Step 3: Configure rootless ownership and socket modes**

Enable subordinate UID/GID ranges and linger for `agentops`, install the pinned
rootless runtime, create a named `aegis-rootless` context, and verify a rootless
container reports a non-host root UID mapping. Create `/run/aegis` through
`RuntimeDirectory` and set control socket group/mode `0660`; keep Herdr socket
`0600 agentops:agentops`. Bind OpenViking to `127.0.0.1:1933` and QMD HTTP, when
enabled, to `127.0.0.1:8181`.

- [ ] **Step 4: Run exposure and rootless checks**

Run: `cd deploy/ansible && make molecule`

Expected: no Aegis component listens publicly; `hermesops` can reach only the control socket; worker runtime has no rootful Docker socket.

- [ ] **Step 5: Commit isolation wiring**

```bash
git add deploy/ansible/roles/aegis deploy/ansible/molecule
git commit -m "feat(deploy): configure private rootless aegis runtime"
```

### Task 4: Secret materialization and encrypted backup/restore

**Files:**
- Create: `deploy/ansible/roles/aegis/tasks/secrets.yml`
- Create: `deploy/ansible/roles/aegis/tasks/backup.yml`
- Create: `deploy/ansible/roles/aegis/templates/backup-paths.conf.j2`
- Create: `scripts/restore-drill.sh`
- Create: `tests/security/test_repository_secrets.py`

- [ ] **Step 1: Write repository and deployment secret tests**

```python
import subprocess
from pathlib import Path


FORBIDDEN = ("BEGIN" + " PRIVATE KEY", "Bear" + "er ", "gh" + "p_", "sk-" + "proj-", "TELEGRAM_BOT" + "_TOKEN=")


def test_repository_contains_no_secret_material() -> None:
    tracked = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout.split(b"\0")
    for raw_path in filter(None, tracked):
        path = Path(raw_path.decode())
        text = path.read_text(errors="ignore")
        assert not any(marker in text for marker in FORBIDDEN), path
```

- [ ] **Step 2: Run test and backup scenario before implementation**

Run: `uv run pytest tests/security/test_repository_secrets.py -q && cd deploy/ansible && make molecule`

Expected: repository scan passes; Molecule backup/restore assertions fail because hooks are absent.

- [ ] **Step 3: Add per-service secret files and backup paths**

```yaml
- name: Materialize Aegis service secrets
  ansible.builtin.copy:
    content: "{{ item.value }}"
    dest: "{{ item.path }}"
    owner: "{{ item.owner }}"
    group: "{{ item.owner }}"
    mode: "0600"
  loop: "{{ aegis_secret_files }}"
  no_log: true
```

Generate backup configuration for SQLite plus WAL-safe snapshot, audit segments,
config snapshots, Herdr metadata, company brain, sanitized archives, and
non-rebuildable OpenViking state. Exclude QMD indexes, rootless image layers,
worktrees, and disposable services. `restore-drill.sh` restores to a temporary
root, runs the audit verifier, database integrity/migrations, Git fsck, inventory
comparison, and OpenViking rebuild without contacting production services.

- [ ] **Step 4: Run repository, backup, and restore tests**

Run: `uv run pytest tests/security/test_repository_secrets.py -q && cd deploy/ansible && make molecule && cd ../.. && bash scripts/restore-drill.sh --fixture tests/fixtures/backup/pilot`

Expected: no secret markers; backup manifest matches the spec; clean restore passes integrity and inventory comparisons.

- [ ] **Step 5: Commit backup and secret controls**

```bash
git add deploy/ansible scripts/restore-drill.sh tests/security/test_repository_secrets.py tests/fixtures/backup
git commit -m "feat(ops): add encrypted state backup and restore drill"
```

### Task 5: CI release gates and signed manifest

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `scripts/build-release-manifest.py`
- Create: `tests/release/test_manifest.py`

- [ ] **Step 1: Write release manifest test**

```python
def test_release_manifest_captures_reproducible_inputs(manifest) -> None:
    assert manifest["git_commit"]
    assert manifest["uv_lock_sha256"]
    assert manifest["config_catalog_sha256"]
    assert manifest["schema_versions"] == {"api": "v1", "database": 1, "flow": 1, "project": 1}
    assert manifest["artifacts"][0]["sha256"]
```

- [ ] **Step 2: Run and confirm release tooling absence**

Run: `uv run pytest tests/release/test_manifest.py -q`

Expected: FAIL because the manifest builder is absent.

- [ ] **Step 3: Implement CI and manifest generation**

CI jobs run Ruff, mypy, unit/contract/integration/security/recovery/TUI/Hermes
tests, Ansible lint, and Molecule. Release builds from `uv.lock`, generates wheel
and config bundle digests, records schemas/dependency versions/licenses, and signs
the JSON manifest with the repository's configured release identity. It refuses a
dirty tree, non-tag commit, failing license gate, or skipped release-required test.

- [ ] **Step 4: Run the local release gate**

Run: `uv run ruff check . && uv run mypy src && uv run pytest && cd deploy/ansible && make lint && make molecule && cd ../.. && uv run python scripts/build-release-manifest.py --check`

Expected: all checks pass and manifest `--check` reports no drift.

- [ ] **Step 5: Commit CI and release evidence**

```bash
git add .github scripts/build-release-manifest.py tests/release
git commit -m "ci(release): gate and describe aegis artifacts"
```

### Task 6: VPS stabilization, staged install, and soak ledger

**Files:**
- Create: `docs/runbooks/01-preflight-and-stabilization.md`
- Create: `docs/runbooks/02-install-upgrade-rollback.md`
- Create: `docs/runbooks/03-backup-restore.md`
- Create: `docs/runbooks/04-incident-recovery.md`
- Create: `docs/runbooks/05-pilot-soak.md`
- Create: `config/soak/pilot.yaml`

- [ ] **Step 1: Write the machine-readable soak gate**

```yaml
version: 1
minimum_days: 14
minimum_tasks: 25
minimum_projects: 2
maximum_concurrent_workers: 2
required_zero_counts:
  lost_correlations: 0
  unauthorized_state_changes: 0
  secret_exposures: 0
  cleanup_cross_task_deletions: 0
required_drills:
  - aegis_process_kill
  - herdr_process_kill
  - vps_reboot
  - provider_outage
  - credit_exhaustion
  - native_resume
  - handoff_resume
  - encrypted_restore
```

- [ ] **Step 2: Validate the config before runbooks exist**

Run: `uv run ae config validate-soak config/soak/pilot.yaml`

Expected: FAIL because the soak validator is not registered.

- [ ] **Step 3: Add validator and exact operational procedures**

Each runbook lists prerequisites, read-only preflight, command, expected output,
rollback trigger, rollback command, evidence location, and operator approval point.
Stabilization covers Hermes CLI/unit mismatch, firewall drift, `dev` permission
repair after dependency inspection, backup baseline, public Coolify HTTPS versus
raw `:8000`, and scoped stale Multica cleanup. Installation enables the TUI first;
Telegram remains disabled until local security/recovery gates pass.

- [ ] **Step 4: Execute the pre-deployment verification set**

Run: `uv run ae config validate-soak config/soak/pilot.yaml && uv run pytest && cd deploy/ansible && make lint && make molecule`

Expected: validator and full automated suite pass. Live VPS commands remain operator-gated and record their evidence in the pilot ledger.

- [ ] **Step 5: Commit operational rollout documentation**

```bash
git add docs/runbooks config/soak src/aegis/cli.py tests
git commit -m "docs(ops): define staged vps rollout and soak gate"
```

### Task 7: Pilot completion and `1.0.0` decision

**Files:**
- Create: `docs/releases/pilot-evidence.md`
- Create: `docs/releases/1.0.0-readiness.md`

- [ ] **Step 1: Generate evidence from the task registry**

Run: `uv run ae report soak --config config/soak/pilot.yaml --output docs/releases/pilot-evidence.md`

Expected: the report states pass/fail for every numeric gate and drill using task/audit/artifact references.

- [ ] **Step 2: Run final verification and restore drill**

Run: `uv run ruff check . && uv run mypy src && uv run pytest && cd deploy/ansible && make lint && make molecule && cd ../.. && bash scripts/restore-drill.sh --latest-encrypted-backup`

Expected: every automated check and clean restore passes on the release candidate commit.

- [ ] **Step 3: Record the release decision**

Write `1.0.0-readiness.md` with the exact commit, release manifest digest, test
counts, Ansible convergence result, restore inventory comparison, soak metrics,
license decisions for Herdr/OpenViking distribution, unresolved risks, and an
explicit operator approve/reject decision.

- [ ] **Step 4: Tag only an approved candidate**

Run: `git tag -s v1.0.0 -m "Aegis 1.0.0"`

Expected: the signed tag is created only when `1.0.0-readiness.md` records approval and all evidence links resolve.

- [ ] **Step 5: Publish the immutable release**

Run: `git push origin v1.0.0`

Expected: the release workflow publishes checksum-verified artifacts and the VPS repository can pin `v1.0.0` plus its manifest digest.
