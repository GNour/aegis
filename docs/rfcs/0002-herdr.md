# 0002 — Herdr durable agent sessions
Status: accepted for the internal pilot; commercial reuse requires a license review
Date: 2026-07-23
Sponsor: Aegis — needs durable Codex/OpenCode terminals, worktrees, native
session references, event subscriptions, and restart recovery.

## 1. Problem & goal

Aegis must run heterogeneous coding CLIs for hours, survive disconnects and
service restarts, identify blocked/done agents, and resume native conversations.
Building and maintaining a terminal multiplexer plus agent integrations inside
Aegis would be a large distraction.

## 2. Options considered

| Option | Summary | Cost | Maturity | License |
|---|---|---|---|---|
| **Herdr** | Agent-aware terminal multiplexer with Unix-socket API, worktrees, events, and native session integrations | One Rust process plus session scrollback | Active; APIs are young and fast-moving | AGPL-3.0-or-later or commercial |
| tmux + custom adapters | Stable process persistence with custom parsing/hooks for every agent | Low runtime, high engineering burden | tmux mature; adapters local | ISC for tmux; local code |
| Aegis-owned subprocess supervisor | No external multiplexer | Highest implementation and recovery burden | New | Local code |

## 3. Fit analysis (hard gates — Aegis architecture)

- **RAM (§6):** expected to be small compared with worker CLIs and project
  services, but no upstream RAM guarantee is relied on. Measure idle and
  two-worker usage during the soak.
- **Exposure (§5):** local Unix socket only. The socket remains private to
  `agentops`; Hermes cannot access it.
- **Secrets owner (§4):** `agentops`. Herdr stores session metadata and may store
  optional pane history, so the latter stays disabled until redaction and
  retention tests pass.
- **License:** AGPL-3.0-or-later is acceptable for the owner's internal pilot.
  Client distribution or hosted product use must either comply with AGPL or use
  Herdr's commercial license. Do not make Herdr an unreviewed mandatory customer
  dependency.
- **Backup impact:** back up configuration, session manifests, native
  session references, and metadata-focused logs under `~/.config/herdr`.

## 4. Upstream-verified install sketch

Verified 2026-07-23 against the official
[install guide](https://herdr.dev/docs/install/),
[agent integrations](https://herdr.dev/docs/integrations/),
[session recovery guide](https://herdr.dev/docs/session-state/), and
[socket API](https://herdr.dev/docs/socket-api/).

Install a pinned stable Linux x86_64 release into `agentops`'s `~/.local/bin`,
verify its checksum, and disable automatic unpinned upgrades. Install the Codex
and OpenCode integrations. At startup, Aegis reads the JSON schema shipped by
that exact binary (`herdr api schema --json`) and refuses an unsupported protocol.
Aegis prefers CLI wrappers for ordinary operations and uses the raw socket only
for event subscriptions and request/response operations that require it.

## 5. Recommendation

Adopt Herdr behind a narrow adapter. Persist its native session references and
worktree provenance in Aegis. Do not expose its socket to Hermes or workers.
Pin the release and protocol schema, keep pane-content persistence off initially,
and retain a documented fallback to handoff-based restart if native resume fails.

## 6. Decision & graduation

- ADR: [0001](../adrs/0001-isolate-aegis-service-users.md).
- Graduates to: the future Aegis numbered build guide.
- Validation: create/inspect/remove worktrees; detect Codex/OpenCode states;
  survive detach; restart Herdr; resume supported native sessions; rebuild from a
  handoff when resume is unavailable; confirm the socket is inaccessible to
  `hermesops` and workers.
