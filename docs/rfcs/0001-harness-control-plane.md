# 0001 — Harness agent control plane
Status: accepted
Date: 2026-07-23
Sponsor: owner — needs a secure, durable way to orchestrate heterogeneous coding
agents through a TUI and Telegram without turning Hermes into a remote shell.

## 1. Problem & goal

The VPS has coding runtimes and a conversational gateway but no accepted control
plane that correlates requests, flows, worktrees, agent sessions, decisions,
knowledge, and cleanup. Multica has been removed. The prior direct-Hermes design
would have repurposed `dev`, combined the chat gateway with root-equivalent Docker
access, and defaulted to automatic promotion; the owner rejected those choices.

The goal is a small deterministic service that gives agents autonomy inside an
isolated task environment, escalates human decisions, resumes after process or
credit failures, and preserves an auditable Markdown record before cleanup.

## 2. Options considered

| Option | Summary | Cost | Maturity | License |
|---|---|---|---|---|
| **Custom Harness service** | Typed control API, versioned flows, SQLite + JSONL, Herdr adapters, TUI and Hermes client | Engineering and maintenance time; low steady-state runtime | New local component built around existing repo policy | Repository license |
| Mastra | TypeScript workflow/agent framework with durable snapshots and observability | Additional Node service and overlapping state/memory abstractions | Mature and fast-moving | Apache-2.0 core; separate enterprise-licensed code |
| CrewAI | Python crews plus deterministic flows and human feedback | Adds another agent roster and execution model | Mature and fast-moving | MIT core; commercial control-plane offering |

Mastra has useful workflow primitives, but Harness still needs custom capability,
worktree, Herdr, credential, and cleanup enforcement. CrewAI overlaps the external
Codex/OpenCode roster and does not replace native CLI session durability. Both are
excluded from the initial system.

Research was rechecked on 2026-07-23 against the official
[CrewAI documentation](https://docs.crewai.com/index),
[CrewAI repository/license](https://github.com/crewAIInc/crewAI),
[Mastra workflow snapshots](https://mastra.ai/en/reference/workflows/snapshots),
and [Mastra repository/license map](https://github.com/mastra-ai/mastra). CrewAI's
flows and Mastra's persisted suspend/resume are credible options if Harness later
needs an embedded application-level agent loop. They do not remove the VPS-specific
security, worktree, session, and cleanup responsibilities that drive this design.

## 3. Fit analysis (hard gates — Harness architecture)

- **RAM (§6):** the live host has about 23 GiB rather than the documented 12 GB.
  The Python control service, SQLite, and TUI should be small; worktree services
  and local retrieval models dominate. Pilot concurrency is capped at two and
  must be raised only from measurements.
- **Exposure (§5):** no public listener. Harness uses a Unix socket under
  `/run/harness`; the TUI is reached over existing SSH/Tailscale and Telegram
  reaches it through the restricted Hermes gateway.
- **Secrets owner (§4):** `agentops` owns Harness and long-lived adapter secrets.
  `hermesops` owns only Telegram/provider configuration and permission to call
  the control socket. Workers receive task-scoped proxy capabilities, never raw
  provider, Git, deployment, or infrastructure keys.
- **License:** local code is productization-safe. Dependency licenses remain
  independently gated in RFCs 0002–0005.
- **Backup impact:** add SQLite, hash-linked JSONL, flow snapshots,
  Herdr session metadata, the company-brain Git repo, and sanitized session
  archives. Rebuildable QMD indexes are excluded.

## 4. Upstream-verified install sketch

Harness is built in this repository, installed as a pinned Python package under
`agentops`, and started by a hardened systemd unit. Provisioning creates
`hermesops` and `agentops`, a rootless worker runtime, `/run/harness` socket
permissions, private state directories, and backup paths.

The implementation contract is the approved
[architecture](../architecture.md). External
adapter commands and flags must be rechecked at implementation time against
RFCs 0002–0005 and their cited upstream sources.

## 5. Recommendation

Build Harness as a deterministic Python 3.12 service. Keep `dev` unchanged during
the pilot. Separate the Telegram gateway (`hermesops`) from the control/worker
plane (`agentops`). Store current state in SQLite WAL and append redacted events
to a hash-linked JSONL ledger. Make flows, routing, roles, model aliases,
capabilities, and per-role skills versioned data. Use Herdr for process/session
durability, QMD for Markdown retrieval, and OpenViking for approved long-term
memory.

## 6. Decision & graduation

- ADRs: [0001](../adrs/0001-isolate-harness-service-users.md),
  [0002](../adrs/0002-config-driven-harness-flows.md),
  [0003](../adrs/0003-brokered-agent-autonomy.md), and
  [0004](../adrs/0004-git-qmd-openviking-knowledge.md).
- Graduates to: a versioned Harness release after implementation validation.
- Validation: the complete checklist in [architecture §16](../architecture.md#16-acceptance-criteria).
