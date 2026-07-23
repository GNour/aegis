# Harness implementation roadmap

Status: plans 1–4 ready; plan 5 pending container-first rewrite

The architecture spans five independently testable subsystems. Execute their
plans in order; each ends with a working vertical capability and a commit gate.

| Order | Plan | Deliverable | Depends on |
|---|---|---|---|
| 1 | [Core control plane](01-core-control-plane.md) | typed domain, durable state/audit, flow/policy engine, Unix-socket API | approved specs |
| 2 | [Workers and services](02-workers-herdr-services.md) | worktrees, rootless services, Herdr/runtime adapters, recovery-safe cleanup | plan 1 |
| 3 | [Context and knowledge](03-context-and-knowledge.md) | exact skill injection, QMD/OpenViking, bounded context, knowledge gate | plans 1–2 |
| 4 | [TUI and Hermes](04-tui-and-hermes.md) | operator TUI and restricted Telegram/Hermes parity | plans 1–3 |
| 5 | [Deployment and rollout](05-deployment-and-rollout.md) | container-first installer, rootless Compose appliance, management CLI, backup/restore, security suite, soak | plans 1–4 |

Every plan uses TDD and focused commits. No later plan may weaken a security or
state invariant established by an earlier one. When upstream CLI behavior differs
from a plan, record the evidence in the relevant RFC and adjust the adapter test
before changing production code.

## Release sequence

1. `0.1.0-dev`: plan 1 complete; API is local and uses fake adapters.
2. `0.2.0-dev`: plan 2 complete; isolated local tasks resume after process loss.
3. `0.3.0-dev`: plan 3 complete; preservation blocks cleanup until receipts exist.
4. `0.4.0-dev`: plan 4 complete; TUI and Hermes pass API-parity tests.
5. `0.5.0-pilot`: plan 5 complete; installed on the VPS for the two-project soak.
6. `1.0.0`: soak, restore drill, license gates, and full verification matrix pass.
