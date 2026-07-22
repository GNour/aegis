# Source material and resolved changes

`initial-plan.md` is the original WSL-oriented proposal. It is retained verbatim
for provenance and must not override accepted architecture or specifications.

The approved design resolves its major open points as follows:

| Original proposal | Accepted Harness direction |
|---|---|
| Dedicated WSL first, eventual VPS | Build directly for the audited Ubuntu 24.04 VPS while keeping deployment reusable |
| Orchestrator account not fully split | `hermesops` gateway and `agentops` control/worker plane |
| Potentially repurpose the existing development environment | Keep `dev` unchanged during the pilot |
| Fixed lifecycle with approval/promotion stages | Versioned configurable flows with non-removable policy gates |
| Three initial workers | Two-worker admission cap until measured soak evidence supports more |
| Shared skills repository mounted read-only | Registry remains shared, but each stage receives only exact declared skill versions |
| OpenViking as the main retrieval addition | Git Markdown canonical, QMD for scoped local document retrieval, OpenViking for derived memory |
| Telegram after local validation | Retained; TUI proves identical API/policy/audit behavior first |
| Multica coexistence was possible in earlier VPS docs | Multica server is removed; only verified stale remnants are cleaned |
| Framework choice open | CrewAI and Mastra excluded from the initial deterministic control plane |

When historical text conflicts with `docs/architecture.md` or `docs/specs/`, the
accepted documents win.
