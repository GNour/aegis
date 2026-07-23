# 0004 — OpenCode economical worker runtime
Status: accepted for the internal pilot
Date: 2026-07-23
Sponsor: Aegis — needs a configurable, provider-agnostic implementation runtime
for economical DeepSeek and Gemini workers alongside the Codex subscription seat.

## 1. Problem & goal

Codex is the frontier runtime, but routine implementation and review should be
able to use cheaper model aliases without changing Aegis flows. The runtime
must support headless sessions, exports, per-agent permissions, token/cost stats,
and resumability through Herdr.

## 2. Options considered

| Option | Summary | Cost | Maturity | License |
|---|---|---|---|---|
| **OpenCode** | Provider-agnostic coding agent with headless/server modes, sessions, exports, costs, and per-agent permissions | Provider tokens plus one worker process | Active and fast-moving | MIT |
| Codex only | One runtime and subscription pool | Simple but constrained throughput/model choice | Mature | Product terms |
| Direct custom model worker | Aegis implements its own tool loop | Highest security/control and implementation burden | New | Local code |

## 3. Fit analysis (hard gates — Aegis architecture)

- **RAM (§6):** one CLI/server process per active worker plus its project
  services. The two-worker pilot cap includes OpenCode.
- **Exposure (§5):** no public server. Prefer CLI sessions in rootless workers;
  any headless server binds to a task-private socket/network only.
- **Secrets owner (§4):** upstream provider keys stay with `agentops`'s Aegis
  credential broker. OpenCode receives a revocable, task-scoped model-proxy
  capability, not the provider key. Workers get no Git push/deploy credentials.
- **License:** MIT, suitable for internal and productized use.
- **Backup impact:** persist sanitized session exports, session IDs,
  run metadata, and durable handoffs. Runtime caches are rebuildable.

## 4. Upstream-verified install sketch

Verified 2026-07-23 against the official
[CLI reference](https://opencode.ai/docs/cli/),
[agent configuration](https://opencode.ai/docs/agents/),
[permissions](https://opencode.ai/docs/permissions/), and
[MIT license](https://github.com/anomalyco/opencode/blob/dev/LICENSE).

Install a pinned release into the worker image. Render one agent profile per
Aegis role with exact `allow`/`ask`/`deny` permissions; Aegis's container and
capability policy remains the hard boundary. Record the OpenCode session ID,
collect `opencode stats`, and export completed sessions with `--sanitize`.
Configure the Herdr OpenCode integration for lifecycle state and native session
identity. Do not expose `opencode serve` publicly.

## 5. Recommendation

Adopt OpenCode for routine and intermediate workers. Treat its permission file as
defense in depth, not the sandbox. Start with a small role set, network off by
default, task-scoped worktree mounts, role-specific skills, and an Aegis model
proxy. Escalate complex, repeatedly failing, security-sensitive, or
architecture-heavy work to Codex through flow policy.

The credential broker is a release blocker: OpenCode is not admitted as a worker
until tests prove that raw provider keys are absent from the worker filesystem,
environment, process output, session export, and artifacts.

## 6. Decision & graduation

- ADR: [0003](../adrs/0003-brokered-agent-autonomy.md).
- Graduates to: the future Aegis numbered build guide.
- Validation: role permissions, rootless worktree isolation, network default
  deny, sanitized export, stats capture, Herdr resume, provider-credit failure
  classification, and raw-key non-exposure.
