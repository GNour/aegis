# Aegis

Aegis is a private control plane for supervised, resumable agentic software
work. It accepts requests from a local TUI or a restricted Hermes Telegram
gateway, selects a versioned flow, starts isolated coding-agent sessions through
Herdr, tracks decisions and recovery state, and preserves knowledge before it
cleans up task resources.

This repository is the single source of truth for Aegis documentation,
specifications, plans, implementation, tests, integrations, and deployment
automation. The separate VPS infrastructure repository consumes a pinned Aegis
release and supplies instance-specific variables.

## Current status

The architecture is approved and [Plan 1 (core control plane)](docs/plans/01-core-control-plane.md)
is complete: the Python shell, domain records and lifecycle, transactional SQLite
state, redacted hash-linked audit ledger, versioned flow/routing catalog, policy
engine, one-use approvals, and the local FastAPI control-plane API. The
[companion-package integration plan](docs/plans/01a-companion-packages-and-stage-packets.md)
is also complete: PromptX and Subagents are pinned as digest-verified submodules,
the reviewed role catalog is compiled and embedded, and immutable stage packets are
compiled and stored exactly once.
[Plan 2 (workers, Herdr, and project services)](docs/plans/02-workers-herdr-services.md)
is complete: trusted project manifests, contained Git worktrees, rootless
task-scoped services with exact-label cleanup, a narrow Herdr socket adapter,
credential-isolated worker sandboxes, and failure classification with native-first
resume and preservation-gated cleanup.
[Plan 3 (context and knowledge)](docs/plans/03-context-and-knowledge.md) is complete:
exact read-only skill bundles, scoped/bounded QMD retrieval, source-linked OpenViking
memory, the bounded cited context compiler, RTK dual-output capture, and the
preservation coordinator that gates cleanup on exact-commit indexing receipts.
[Plan 4 (TUI and Hermes)](docs/plans/04-tui-and-hermes.md) is now complete: the typed
control client, the Textual operator TUI, the restricted Hermes company-control
plugin and company-orchestrator skill, and idempotent notifications, verified for
API/audit parity across both interfaces.
[Plan 5 (container-first deployment)](docs/plans/05-deployment-and-rollout.md) is now
complete: the product-metadata source of truth, versioned appliance config with secret
separation, the private-network Compose bundle, the container runtime port and
`ae appliance` management surface, signed digest-pinned releases with automatic
rollback, portable backup/restore, and an idempotent installer with doctor/repair and
scoped uninstall — see the [deployment guide](docs/deployment/README.md). All five
subsystems are implemented; the remaining work is the live `AEGIS_LIVE_*` release-gate
matrix on provisioned hosts and the pilot soak.

Start here:

- [Documentation map](docs/README.md)
- [Approved architecture](docs/architecture.md)
- [Product requirements](docs/specs/00-product-requirements.md)
- [Implementation roadmap](docs/plans/00-implementation-roadmap.md)
- [VPS integration contract](docs/integration/vps-refined.md)

## Repository boundaries

Aegis owns:

- the Python control service, TUI, state machine, audit ledger, flow engine, and
  policy engine;
- Herdr, worker-runtime, worktree, QMD, OpenViking, and RTK adapters;
- the Hermes `company-control` plugin and `company-orchestrator` skill;
- schemas, default flows, role profiles, capability profiles, and model aliases;
- the Aegis integration, compatibility testing, and coordinated release of the
  maintained PromptX and Subagents companion-package submodules;
- the container-first installer, rootless Compose bundle, management CLI,
  optional fleet integrations, and operational runbooks;
- all unit, integration, security, recovery, and soak tests.

Aegis does not own VPS-wide Coolify configuration, unrelated applications, or
the owner's interactive `dev` environment.

## Planned development commands

Once the foundation plan is implemented:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy src
uv run ae --help
```

No real credentials, IP addresses, bot tokens, provider keys, or subscription
session data belong in this repository.
