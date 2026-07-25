---
title: Aegis Implementation Roadmap
tags:
  - aegis
  - plan
  - roadmap
---

# Aegis implementation roadmap

Status: all plans implemented — 1 (core control plane), 1a (companion packages), 2
(workers, Herdr, and project services), 3 (context and knowledge), 4 (TUI and Hermes),
and the container-first plan 5 (deployment). Remaining work is the live release-gate
matrix on provisioned hosts (`AEGIS_LIVE_*`) and the pilot soak.

Implementation progress: core control-plane tasks 1–6, the entire companion-package
integration plan (1a), all six tasks of plan 2, all six tasks of plan 3, all five tasks
of plan 4, and all eight tasks of the container-first plan 5 are complete. The
container-first installer replaces the superseded Ansible-first delivery model.

The architecture spans five independently testable subsystems. Execute their
plans in order; each ends with a working vertical capability and a commit gate.

| Order | Plan | Deliverable | Depends on |
|---|---|---|---|
| 1 | [[01-core-control-plane|Core control plane]] | typed domain, durable state/audit, flow/policy engine, Unix-socket API | approved specs |
| 1a | [[01a-companion-packages-and-stage-packets|Companion packages and stage packets]] | pinned companions, compiled role catalog, PromptX adapter, immutable stage packets | plan 1 task 4 and admitted upstream P0 releases |
| 2 | [[02-workers-herdr-services|Workers and services]] | worktrees, rootless services, Herdr/runtime adapters, recovery-safe cleanup | plans 1 and 1a |
| 3 | [[03-context-and-knowledge|Context and knowledge]] | exact skill injection, QMD/OpenViking, bounded context, knowledge gate | plans 1–2 |
| 4 | [[04-tui-and-hermes|TUI and Hermes]] | operator TUI and restricted Telegram/Hermes parity | plans 1–3 |
| 5 | [[05-deployment-and-rollout|Deployment and rollout]] | container-first installer, rootless Compose appliance, management CLI, backup/restore, security suite, soak | plans 1–4 |

Every plan uses TDD and focused commits. No later plan may weaken a security or
state invariant established by an earlier one. When upstream CLI behavior differs
from a plan, record the evidence in the relevant RFC and adjust the adapter test
before changing production code.

The required [[01a-companion-packages-and-stage-packets|PromptX/Subagents integration plan]]
executes after core plan 1 task 4 and before core plan 1 task 5. It establishes
the pinned submodules, catalog compiler, PromptX contract adapter, and immutable
stage-packet records needed by flow compilation and later worker dispatch.

## Release sequence

1. `0.1.0-dev` ✓: plan 1 complete; API is local and uses fake adapters.
2. `0.2.0-dev` ✓: plan 2 complete; isolated local tasks resume after process loss.
3. `0.3.0-dev` ✓: plan 3 complete; preservation blocks cleanup until receipts exist.
4. `0.4.0-dev` ✓: plan 4 complete; TUI and Hermes pass API-parity tests.
5. `0.5.0-pilot` ✓ (against fakes): plan 5 complete; the live VPS install and
   two-project soak run through the `AEGIS_LIVE_*` release-gate matrix.
6. `1.0.0`: soak, restore drill, license gates, and full verification matrix pass.
