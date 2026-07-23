# Harness Architecture

Status: approved design

Date: 2026-07-23

## 1. Goal and scope

Harness is a self-contained control plane for supervised, resumable agentic work
on the VPS. A human can create and steer work through a local TUI or Telegram.
Hermes interprets requests and uses typed Harness tools. Harness selects a
versioned flow, enforces policy, starts durable coding-agent sessions through
Herdr, supplies isolated project services, records every run and decision, and
preserves knowledge before cleanup.

The first worker runtimes are Codex and OpenCode. The design permits additional
runtimes through adapters without changing the flow engine.

CrewAI and Mastra are deliberately excluded. Harness uses a small deterministic
state machine; Herdr owns terminal/session durability, and OpenViking owns
long-term agent memory.

## 2. Deployed-host facts and reconciliation

Read-only inspection on 2026-07-23 found:

- Ubuntu 24.04, 8 vCPU, approximately 23 GiB RAM, 193 GiB root disk, and 4 GiB
  swap. These measured facts supersede the older values preserved in the
  [initial plan](source/initial-plan.md).
- The existing `dev` account owns interactive Claude/Codex logins, project
  workspaces, Docker-group access, and current developer tools.
- Multica's server containers are removed. A stale daemon, CLI, and home-state
  directory remain and require scoped cleanup; there is no migration or fallback
  phase in Harness.
- Both Hermes services are restart-looping because the installed Hermes version
  rejects the units' obsolete `--foreground` argument.
- Coolify is intentionally public at `https://coolify.nco-tech.com`. The raw
  host-port listener on `:8000` is not the user-facing route and may be closed
  while preserving public HTTPS access through Traefik on `443`.
- `.claude` and `.codex` under `dev` were observed with mode `0777`. Permission
  repair must preserve the existing login state and occur only after dependency
  inspection.

The stabilization work is part of the rollout, but Harness does not repurpose
`dev` or remove its Docker membership during the pilot.

## 3. Accounts and trust boundaries

Existing accounts:

| Account | Responsibility | Harness change |
|---|---|---|
| `deploy` | Host bootstrap, optional fleet automation, and break-glass administration | No role change |
| `dev` | Owner's interactive development environment | No role or group change during pilot |
| `hermes` | Restricted family gateway | No Harness access |

New accounts:

| Account | Responsibility | Explicit exclusions |
|---|---|---|
| `hermesops` | Private ops Telegram gateway and Harness client | No SSH key, sudo, agent runtime, repos, worktrees, provider keys, or Herdr socket; its optional rootless context can run only the gateway stack |
| `agentops` | Harness, Herdr, flow state, worktrees, rootless workers, QMD, OpenViking | No sudo or rootful Docker group |

Both new accounts have locked passwords, private `0700` homes, and no direct SSH
authorization. `deploy` performs installation and account-scoped setup with
`sudo -u`. Long-running user services use systemd linger where required.

The one-command bootstrap creates both identities and their isolated rootless
contexts. Long-running containers use systemd user startup integration and linger
where required. The control path is:

```text
Telegram
  -> Hermes (`hermesops`)
  -> /run/harness/control.sock
  -> Harness (`agentops`)
  -> Herdr private socket
  -> task worktree + rootless worker/runtime services
```

Hermes cannot reach Herdr directly. The Herdr socket, agent terminals, worktree
roots, and runtime credentials are private to `agentops`. The Harness control
socket uses Unix peer identity plus an operator group; it is never exposed over
the public network.

## 4. Repository layout

```text
./
|-- README.md
|-- pyproject.toml
|-- .gitmodules
|-- packages/
|   |-- promptx/            # required runtime companion Git submodule
|   `-- subagents/          # required build-time catalog Git submodule
|-- src/harness/
|   |-- api/                 # typed control functions
|   |-- domain/              # manifests, runs, decisions, events
|   |-- engine/              # lifecycle and flow execution
|   |-- routing/             # deterministic flow selection
|   |-- policy/              # principals, risk, capabilities
|   |-- adapters/            # Herdr, Git, workers, QMD, OpenViking
|   |-- audit/               # redaction and hash-linked JSONL
|   `-- tui/                 # local operator interface
|-- config/
|   |-- flows/
|   |-- routing.yaml
|   |-- capability-profiles/
|   |-- role-profiles/
|   `-- model-aliases.yaml
|-- integrations/hermes/
|   |-- plugin/              # typed Harness tools
|   `-- skill/SKILL.md       # conversation and routing behavior
|-- deploy/
|   |-- compose/             # generated rootless appliance bundles
|   |-- installer/           # Ubuntu bootstrap and management CLI
|   `-- ansible/             # optional fleet integration using the same contract
|-- docs/
`-- tests/
```

This repository owns Harness code, schemas, integrations, tests, deployment
automation, specifications, plans, RFCs, ADRs, and runbooks. The VPS
infrastructure repository consumes the pinned Harness release and supplies
instance variables; it does not duplicate Harness implementation.

Harness is released as a rootless Docker Compose appliance. A renameable
host-side management CLI hides Compose contexts, service-account runtime
variables, and container topology. The bootstrap supports interactive and
unattended configuration, installs Docker and Compose when absent, and converges
clean Ubuntu 22.04 and 24.04 hosts idempotently. Images are selected through
signed stable or opt-in edge manifests and resolved to immutable digests; a
mutable `latest` tag is never a deployment input.

## 5. Control interface and Hermes integration

The initial control surface is:

| Function | Purpose |
|---|---|
| `list_flows` | Return caller-allowed flows and their input requirements |
| `create_task` | Create a task with an explicit `flow_id` or server-side `auto` routing |
| `get_task_status` | Return state, stage, blockers, attempts, decisions, and artifacts |
| `approve_action` | Approve one exact, signed, expiring escalation |
| `reject_action` | Reject an escalation with an optional durable reason |
| `cancel_task` | Stop dispatch, preserve a handoff, and enter scoped cleanup |
| `resume_task` | Resume a human-, quota-, provider-, or recovery-paused task |
| `capture_note` | Save a note into the Git-backed inbox with source metadata |
| `schedule_reminder` | Schedule an operator reminder without granting arbitrary cron execution |

There is no arbitrary command endpoint and no generic `start_process` function.
Only the flow engine may translate a validated stage into a registered Herdr or
worker action.

The Hermes integration has two parts:

- The `company-control` plugin implements the typed tool calls over the Unix
  socket.
- The `company-orchestrator` skill teaches Hermes how to clarify requests,
  inspect available flows, explain routing, surface decisions, report status,
  and handle resume/cancel operations. A skill does not grant capabilities.

For a new task Hermes calls `list_flows`, proposes a fit, and sends
`create_task(flow_id=...)` or `create_task(flow_id="auto")`. Harness independently
evaluates routing rules and returns the selected flow, version, reason, risk, and
stage plan. Required human decisions are surfaced before the relevant stage.

## 6. Configurable flows and routing

Flows are declarative, versioned YAML validated against a strict schema. They
reference registered stages and capabilities; they cannot contain arbitrary host
commands.

```yaml
id: feature-delivery
version: 1
description: Plan, implement, verify, review, preserve knowledge, and clean up
allowed_callers: [ops]
match:
  intents: [feature, enhancement]
stages:
  - clarify
  - plan
  - implement
  - verify
  - independent-review
  - preserve-knowledge
  - cleanup
```

Each stage declares:

- purpose and completion criteria;
- role, model alias, skill set, and capability profile;
- required inputs and structured outputs;
- project-service requirements and health checks;
- token, context, time, and cost budgets;
- retry, fallback, escalation, and resume policy;
- required gates, artifacts, handoff, knowledge, and cleanup behavior.

Routing rules can consider the authenticated principal, source interface,
project, intent, risk, requested outcome, current resource pressure, and previous
attempts. Deterministic rules run before model suggestions. Ambiguous or
high-impact routing becomes a human decision.

Harness provides schema validation, a flow linter, a dry-run simulator, and a
generated flow catalog. Reload is atomic. Each task stores the exact flow content
hash and version it began with; active work cannot change when a flow is edited.

Starter flows are research, feature delivery, bug fix, and independent review.
New flows may compose approved subflows but cannot introduce a capability absent
from the registered policy catalog.

## 7. Domain records and lifecycle

Core records are:

- `TaskManifest`
- `FlowDefinition` and `FlowRun`
- `StageRun` and `Attempt`
- `ApprovalRequest` / `DecisionRequest`
- `SessionLink`
- `HandoffPacket`
- `ArtifactRecord`
- `KnowledgeRecord` and `KnowledgeSync`
- `CleanupRecord`
- `AuditEvent`

The default lifecycle is:

```text
intake -> clarify -> plan -> worktree -> execution -> verification -> review
       -> summary -> preserve knowledge -> cleanup -> complete
```

Flows may add stages, but policy can require non-removable gates. Paused states
include `waiting_human`, `waiting_quota`, `waiting_provider`, `retry_scheduled`,
`blocked`, and `recovery_required`. Terminal states are `complete`, `cancelled`,
and `failed`.

SQLite in WAL mode stores current operational state. Every transition is
transactional and idempotent. A redacted JSONL ledger mirrors events in a hash
chain so modification or deletion is detectable.

## 8. Autonomy and escalation

Actions fall into four policy classes:

| Class | Behavior |
|---|---|
| Autonomous | Read/write the assigned worktree; run approved setup, test, lint, build, review, and documentation operations; commit locally |
| Policy-mediated | A scoped Harness adapter performs an external effect without revealing its credential; the flow decides whether it is automatic or human-gated |
| Human decision | Ambiguous requirements, product or architecture trade-offs, conflicting reviews, irreversible choices, scope expansion, and policy exceptions pause for a person |
| Nondelegable | Raw secret/key disclosure, disabling safeguards, or unrestricted host access is escalated, but approval never hands the capability to the agent; a broker or the human performs the scoped operation |

An approval authorizes one exact action digest, scope, project, risk, reason, and
expiration. It is signed and single-use. Replay, mismatch, expiry, or prior use
fails closed.

Raw provider, Git, Coolify, deployment, and infrastructure keys stay outside
workers. Harness adapters hold long-lived credentials. Where a runtime requires
model access, it receives a task-scoped, revocable proxy capability rather than
the upstream provider key. Codex subscription-auth isolation must be validated
against its sandbox before it is admitted as a writing worker.

## 9. Worktrees and project services

Every writing task gets one Git worktree and at most one writing agent. Read-only
research, testing, and review may run in parallel when they cannot mutate the
worktree.

A repository may include `.harness/project.yaml` describing:

- setup, lint, test, and build commands;
- rootless Compose services and health checks;
- loopback preview endpoints and dynamic ports;
- sanitized fixtures and disposable databases;
- resource limits and permitted outbound destinations;
- artifacts to preserve before cleanup.

Harness assigns a unique rootless Compose project, network, volume set, and port
namespace to the worktree. Services remain available through implementation,
testing, and review.

Validation rejects privileged containers, host networking, devices, the
rootful-Docker socket, host paths outside the worktree, production data, and
unrestricted capabilities. Preview ports bind to loopback. Cleanup targets exact
Harness labels and never performs global Docker pruning.

The pilot limit is two simultaneous workers because per-worktree databases,
browsers, and build services can create large RAM spikes. The limit may increase
only after measured headroom remains within the platform budget.

## 10. Context, retrieval, and skill isolation

Git-backed Markdown is canonical. The retrieval split is:

- QMD indexes Markdown for fast local keyword, vector, and reranked retrieval.
- OpenViking stores approved long-term memories and provides hierarchical,
  source-linked context across sessions.

QMD uses a project-isolated index plus explicitly allowed policy/brain
collections. Secrets, raw transcripts, generated files, dependencies, and
archives are excluded. Harness owns the QMD configuration and disables
project-controlled update commands. Keyword search is the default; semantic
search and reranking are used only when justified. Results return short cited
snippets before full sections.

QMD is not a globally attached MCP. A strict Harness wrapper exposes only
role-scoped `qmd_search` and `qmd_get` operations and validates collection names
and limits before calling QMD.

Harness keeps a versioned skill registry, but never mounts the whole registry.
Every role profile names exact skill versions and tool definitions. Harness
builds an ephemeral, read-only skill directory for that worker and stage. There
is no globally injected skill catalog; the minimal worker contract is rendered
into the role prompt.

The pinned Subagents submodule is the maintained source catalog for approved role
metadata, skill references, and advisory handoffs. Release builds validate and
compile selected catalog entries into Harness role profiles. Subagents tool
strings never grant authority, and its repository, installer, update scripts, and
global catalog are absent from runtime and worker images.

Before a stage, a context compiler builds a bounded envelope from:

- request and acceptance criteria;
- current stage contract and remaining budgets;
- relevant decisions and prior handoff;
- selected role skills;
- QMD snippets with file/line references;
- selected OpenViking records with source commit;
- relevant files, symbols, or test failures.

It deduplicates content, prefers summaries to transcripts, and uses progressive
disclosure. Full session history is not preloaded into later stages.

PromptX is a required control-plane runtime companion built from its pinned
submodule. Harness supplies sanitized, digest-recorded facts and calls PromptX
through a fixed typed adapter. Optional refinement reaches only the loopback
model broker through a scoped capability. PromptX cannot choose a flow, role,
model, skill, tool, capability, approval, or stage transition.

A stage packet compiler combines the exact task, flow, stage, role, skill,
capability, context, budget, companion version, evidence, and handoff snapshots
into one immutable `StageExecutionPacket`. Harness persists its canonical hash
before Herdr dispatch and reuses it for restart or native resume.

RTK is pinned in worker images and configured for supported runtimes. Compressed
command output reaches the model, while full logs remain artifacts retrievable on
demand. Harness records RTK savings, stage context composition, input/output/tool
tokens, model cost, retries, and budget warnings.

## 11. Recovery and resume

Harness records Herdr pane IDs and native Codex/OpenCode session IDs. On failure
it first attempts native resume; if that is unavailable, it starts a replacement
from the latest validated handoff.

A startup sweeper reconciles SQLite records, Herdr panes, worktrees, containers,
and project services. Orphaned processes are quarantined before cleanup.

Credit exhaustion, rate limits, provider downtime, subscription-window limits,
and external blockers record the failure class, provider/model, attempt, and
earliest retry time. Harness stops retry loops and enters a resumable wait state.
Resume can be manual through TUI/Telegram, scheduled at a known reset time, or
automatic when the flow permits. A resume cannot broaden permissions, change the
approved scope, or silently switch to a more privileged runtime.

Session identifiers and decision metadata are retained indefinitely. Sanitized
session exports use configurable retention (initially 180 days). Approved
decisions, summaries, handoffs, knowledge records, and Git history are permanent.

## 12. Knowledge preservation and cleanup

A task is not complete merely because code execution stopped. Completion is:

1. freeze worker writes;
2. run deterministic verification and independent review;
3. capture the final handoff, sessions, attempts, decisions, changed files,
   tests, costs, and unresolved questions;
4. write durable Markdown into the company brain and any required project docs;
5. commit the knowledge ledger;
6. incrementally update the permitted QMD indexes;
7. sync the exact ledger commit to OpenViking and wait for indexing;
8. record QMD/OpenViking receipts and source URIs;
9. preserve required logs, screenshots, coverage, database snapshots, and
   sanitized session exports;
10. stop and remove only the task's labeled containers, networks, volumes, and
    worktree;
11. verify cleanup and append the terminal audit event.

The company-brain layout includes per-project task summaries, decisions,
handoffs, session indexes, and artifact manifests. Accepted specifications and
ADRs that belong to a product remain in that product's repository.

If Markdown commit, QMD indexing, OpenViking synchronization, or artifact
preservation fails, destructive cleanup pauses and the task remains recoverable.

## 13. Human interfaces

The local TUI is the full operator interface. Over SSH/Tailscale it can create
tasks, select flows, inspect timelines and artifacts, answer decision requests,
approve scoped actions, pause/resume/cancel, inspect project services, and open a
controlled Herdr attachment.

Telegram through Hermes supports conversational creation, routing, status,
decisions, approvals, notes, reminders, cancellation, and resume. It is not a
remote shell and does not stream unrestricted terminal input.

Both interfaces call the same API and create identical audit events. TUI identity
comes from Unix peer credentials and operator-group membership. Telegram identity
comes from the allowlisted Telegram ID mapped by the Hermes plugin.

## 14. Exposure, secrets, and backups

Harness, Herdr, QMD, and OpenViking add no public ports. Harness and Herdr use
Unix sockets. QMD is invoked through a local adapter. OpenViking binds to
`127.0.0.1:1933` in API-key mode; the root key remains private to `agentops`, and
`hermesops` receives only a user-scoped key if direct native memory access is
required.

Public Coolify access remains `https://coolify.nco-tech.com` through Traefik.
Harness does not need the raw public `:8000` listener.

Backup coverage adds Harness SQLite/JSONL state, flow and policy snapshots,
Herdr session metadata, the company-brain Git repository, approved sanitized
session archives, and OpenViking state required beyond its rebuildable indexes.
QMD indexes are rebuildable from Git and need not be backed up; its pinned config
and model manifest do.

## 15. Rollout

1. Stabilize current Hermes units, public exposure, firewall drift, permissions,
   backups, and stale Multica remnants without repurposing `dev`.
2. Land and accept the Harness, Herdr, OpenViking, OpenCode, and QMD RFCs plus
   pivotal ADRs; update conflicting numbered docs.
3. Build the idempotent Ubuntu 22.04/24.04 bootstrap, create `hermesops` and
   `agentops`, install their isolated rootless contexts, directories, sockets,
   startup integration, management CLI, Compose bundle, and backup paths.
4. Build the domain model, registry, audit ledger, flow schema, router, policy
   engine, control API, TUI, Hermes plugin, and Hermes skill.
5. Pin the PromptX and Subagents submodules; compile the role catalog; add the
   PromptX adapter and immutable stage packet before worker dispatch.
6. Add Herdr, worktrees, project services, role-scoped skills/tools, RTK, QMD,
   context budgets, and resumable handoffs.
7. Add the Markdown ledger, OpenViking integration, knowledge receipts, and
   failure-safe cleanup.
8. Pilot locally through the TUI, then enable Telegram after the same policy and
   audit behavior is proven.
9. Complete a 14-day soak with at least 25 tasks across two projects before
   increasing concurrency or enabling broader policy-mediated promotion.

## 16. Acceptance criteria

- Flow schema, routing, version snapshots, linter, simulator, and atomic reload
  are tested.
- TUI and Telegram create identical authorized and audited operations.
- Worktree services start, become healthy, remain isolated, and clean up only
  their labeled resources.
- One writer per worktree is enforced; every role receives only its declared
  skill versions and tool definitions.
- PromptX and Subagents source commits and artifact digests are pinned and
  reproducible; their incompatible, dirty, or missing states fail safely.
- Every worker starts from a persisted immutable `StageExecutionPacket`;
  PromptX, Subagents source, installers, and the global role/skill catalog are
  absent from worker images.
- Path traversal, symlink escape, secret reads, dangerous actions, approval
  replay, unauthorized QMD collections, and prompt-injection escalation fail
  safely.
- Worker kill, Harness restart, VPS reboot, provider outage, credit exhaustion,
  and quota-reset resume are exercised.
- Required Markdown, decisions, handoffs, sessions, and artifacts exist before
  cleanup.
- QMD and OpenViking receipts point to the exact committed knowledge source.
- Clean Ubuntu 22.04 and 24.04 install, second-run idempotency, reboot, update,
  rollback, backup/restore, rename compatibility, and scoped uninstall pass;
  Harness and existing Hermes tests remain green.
