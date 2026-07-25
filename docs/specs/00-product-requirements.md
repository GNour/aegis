---
title: Aegis Product Requirements
tags:
  - aegis
  - specification
  - requirements
---

# Aegis product requirements

Status: accepted

## 1. Product outcome

Aegis lets one operator submit, supervise, pause, resume, and audit agentic
software work through a local TUI or restricted Telegram conversation. Agents may
work autonomously inside a task-scoped environment, but they cannot obtain raw
secrets, unrestricted host access, or unreviewed external authority.

## 2. Actors

| Actor | Trust and responsibility |
|---|---|
| Operator | Makes product, architecture, scope, risk, and exception decisions |
| Hermes ops gateway | Conversational client allowed to call typed Aegis controls |
| Aegis service | Authoritative policy, flow, state, audit, context, and cleanup engine |
| Herdr | Private process/session controller called only by Aegis |
| Worker | Role-scoped Codex/OpenCode process in one assigned task environment |
| Reviewer | Read-only agent or operator evaluating evidence and requirements |
| Capability broker | Performs approved external effects without disclosing credentials |
| Knowledge curator | Converts sanitized task evidence into canonical Markdown proposals |

## 3. Functional requirements

### Intake, flow, and control

- **FR-001:** expose `list_flows`, `create_task`, `get_task_status`,
  `approve_action`, `reject_action`, `cancel_task`, `resume_task`, `capture_note`,
  and `schedule_reminder` through one versioned local API.
- **FR-002:** expose no arbitrary command, shell, terminal-input, or generic
  process-starting endpoint.
- **FR-003:** accept an explicit flow or `auto`; server-side routing remains
  authoritative and returns the selected flow, version, hash, reason, and risk.
- **FR-004:** validate, lint, simulate, document, and atomically reload flow and
  routing configuration.
- **FR-005:** snapshot the exact flow, role, skill, capability, and model-alias
  versions at task creation.
- **FR-006:** preserve non-removable policy gates even when a flow is customized.

### State, decisions, and audit

- **FR-010:** assign a stable task ID before dispatch and correlate every flow,
  stage, attempt, session, worktree, commit, decision, artifact, and memory record.
- **FR-011:** persist current state transactionally in SQLite WAL.
- **FR-012:** append each accepted transition to a redacted, hash-linked JSONL
  ledger with actor, causation, correlation, and prior-event hash.
- **FR-013:** model human decisions separately from action approvals.
- **FR-014:** make approvals exact-scope, signed, expiring, and single-use; reject
  replay, mismatch, expiry, wrong actor, and changed payload.
- **FR-015:** expose a complete task timeline and evidence references to both
  operator interfaces.

### Autonomy and workers

- **FR-020:** allow workers to read/write their assigned worktree and run approved
  setup, test, lint, build, review, and documentation operations autonomously.
- **FR-021:** enforce one writing worker per worktree; allow parallel read-only
  work only when it cannot mutate shared state.
- **FR-022:** give each stage only its declared model alias, skill versions, tool
  definitions, project paths, network policy, and resource limits.
- **FR-023:** keep provider, Git, Coolify, deployment, SSH, backup, and
  infrastructure credentials outside worker filesystems, environments, prompts,
  sessions, logs, and artifacts.
- **FR-024:** perform external effects through typed brokers using scoped,
  revocable task capabilities.
- **FR-025:** escalate ambiguity, scope expansion, policy exceptions, conflicting
  reviews, irreversible choices, and prohibited requests to the operator.
- **FR-026:** an approval never makes raw-secret disclosure or unrestricted host
  access delegable; the broker or operator performs the allowed scoped equivalent.

### Worktrees and services

- **FR-030:** create one Git worktree and unique branch for each writing task.
- **FR-031:** read `.aegis/project.yaml` only from the trusted task base commit,
  validate it against a strict schema, and snapshot it before worker execution.
- **FR-032:** provide unique rootless service project names, networks, volumes,
  ports, fixtures, health checks, and resource ceilings per worktree.
- **FR-033:** keep required services alive through implementation, deterministic
  verification, and independent review.
- **FR-034:** reject privileged mode, host networking, devices, rootful Docker
  socket, uncontrolled capabilities, production data, and host paths outside the
  approved task roots.
- **FR-035:** bind previews to loopback and target cleanup only by immutable
  Aegis task labels; never run a global prune.

### Context, skills, and knowledge

- **FR-040:** build a bounded context envelope for each stage from the task,
  stage contract, decisions, handoff, exact skills, cited retrieval, selected
  files, and remaining budgets.
- **FR-041:** never mount or describe the global skill catalog to a worker.
- **FR-042:** expose QMD only through strict role-scoped `qmd_search` and `qmd_get`
  wrappers with project/collection ACLs and bounded results.
- **FR-043:** use lexical QMD search by default; semantic expansion/reranking is
  explicit, measured, and serialized against resource-heavy work.
- **FR-044:** treat Git-backed Markdown as canonical and OpenViking as derived,
  source-linked memory; workers cannot write either canonical layer directly.
- **FR-045:** pin RTK in worker images, send compressed output to models, retain
  complete logs as protected artifacts, and record measured token savings.
- **FR-046:** compile and persist one immutable `StageExecutionPacket` containing
  the exact task, flow, stage, role, model, skill, capability, context, budget,
  companion-package, evidence, and handoff snapshots before worker dispatch.
- **FR-047:** maintain PromptX and Subagents as required pinned Git submodules
  under `packages/`, record their commits and artifact digests, and reject
  missing, dirty, advanced, incompatible, or non-reproducible inputs.
- **FR-048:** run PromptX only through a typed control-plane adapter using
  Aegis-supplied sanitized facts and brokered model access; PromptX cannot
  select or grant flows, roles, models, skills, tools, capabilities, approvals,
  or transitions.
- **FR-049:** compile Subagents at build time into reviewed role configuration;
  never place its repository, installer, global catalog, or advisory tool
  authority in a worker or runtime image.

### Recovery and completion

- **FR-050:** record Herdr identifiers and native runtime session IDs for every
  attempt.
- **FR-051:** resume a native session first; if unavailable, start a replacement
  from the latest validated handoff without broadening authority.
- **FR-052:** classify process loss, quota/credit exhaustion, provider outage,
  policy block, human wait, retry schedule, and recovery-required states.
- **FR-053:** prevent retry loops and store earliest retry time and fallback
  eligibility.
- **FR-054:** reconcile database records, Herdr sessions, worktrees, and rootless
  resources on startup; quarantine uncertain orphans.
- **FR-055:** freeze writes and preserve the final handoff, sessions, decisions,
  tests, costs, changed files, unresolved questions, and required artifacts.
- **FR-056:** commit canonical Markdown, update QMD, sync the exact commit to
  OpenViking, and record receipts before destructive cleanup.
- **FR-057:** pause cleanup and keep the task recoverable if documentation,
  artifact preservation, indexing, or receipt verification fails.

### Interfaces and deployment

- **FR-060:** provide a full local Textual TUI over SSH/Tailscale.
- **FR-061:** provide a restricted Hermes plugin and role skill for Telegram;
  Telegram is not a terminal.
- **FR-062:** enforce identical API, authorization, approval, and audit semantics
  for TUI and Telegram.
- **FR-063:** provide an idempotent one-command bootstrap for Ubuntu 22.04 and
  24.04 that installs rootless Docker and Compose, the container appliance, and
  its management CLI; deploy `hermesops` and `agentops` as locked, non-SSH,
  non-sudo, non-rootful-Docker service accounts and keep `dev` unchanged during
  the pilot.
- **FR-064:** expose Aegis, Herdr, QMD, and OpenViking only on Unix sockets or
  loopback/private interfaces.
- **FR-065:** keep Coolify public HTTPS access independent of Aegis and require
  no public raw `:8000` listener.
- **FR-066:** support equivalent interactive and unattended configuration through
  one versioned schema, with validation and safe apply/rollback behavior.
- **FR-067:** expose routine container status, logs, inspection, shell, exec,
  restart, diagnosis, backup, restore, and uninstall through a renameable
  management CLI with permission-aware auditing.
- **FR-068:** update from signed stable or opt-in edge release manifests using
  immutable image digests, verified pre-update backups, readiness gates, and safe
  rollback metadata; never deploy from a mutable `latest` tag.
- **FR-069:** make installation, configuration, compatibility, migration,
  upgrade, rollback, backup, restore, troubleshooting, release notes, and known
  issues mandatory release artifacts.

## 4. Non-functional requirements

- **NFR-001 Security:** all authorization boundaries have negative tests for
  traversal, symlink escape, secret reads, network escape, approval replay, and
  unauthorized collection/tool access.
- **NFR-002 Durability:** accepted transitions survive process kill and VPS reboot
  without duplicate effects or lost correlation.
- **NFR-003 Idempotency:** retries, startup reconciliation, cleanup, installer
  reruns, configuration apply, and updates are safe; a second converged installer
  run produces no unintended changes.
- **NFR-004 Resource control:** pilot concurrency is two workers; admission pauses
  at configured RAM, disk, load, or service ceilings.
- **NFR-005 Token economy:** context size, input/output/tool tokens, RTK savings,
  retries, and cost are recorded per attempt and stage.
- **NFR-006 Privacy:** unredacted transcripts and secrets are never intentionally
  archived; sanitized session exports default to 180-day retention.
- **NFR-007 Traceability:** every acceptance test links to requirement IDs, and
  every release identifies the exact config/schema/code versions used.
- **NFR-008 Reusability:** instance values enter through documented variables;
  product/CLI naming comes from one metadata definition; no usernames, domains,
  IPs, tokens, or project-specific paths are hard-coded.
- **NFR-009 Companion maintainability:** PromptX and Subagents changes are made
  and verified in their own repositories before a separate Aegis submodule
  pointer update; clean recursive clones, builds, upgrades, and rollbacks are
  reproducible from recorded source and artifact digests.

## 5. Non-goals for the pilot

- automatic merge, public deployment, or production database mutation;
- a browser-hosted Aegis dashboard;
- unrestricted Telegram shell access;
- a large autonomous swarm or more than two concurrent workers;
- replacing Git with OpenViking or QMD;
- modifying the role or Docker membership of the owner's `dev` account;
- embedding CrewAI or Mastra in the initial state machine.

## 6. Release acceptance

The first pilot release requires all FR/NFR mappings in
`docs/specs/08-verification-matrix.md` to pass, container installer convergence
on Ubuntu 22.04 and 24.04, a clean-host restore drill, complete release
documentation, and a 14-day soak with at least 25 tasks across two projects.
