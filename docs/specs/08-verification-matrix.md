# Verification matrix

Status: accepted test contract

| Requirement group | Primary verification |
|---|---|
| FR-001–006 | API contract tests; schema/linter/simulator/reload tests; snapshot fixture |
| FR-010–015 | SQLite transaction/idempotency tests; ledger chain and approval replay tests |
| FR-020–026 | worker capability tests; broker mocks; secret non-exposure and denial tests |
| FR-030–035 | worktree/service integration tests; traversal/symlink/label cleanup tests |
| FR-040–045 | skill fixture inspection; QMD ACL tests; context budget and RTK artifact tests |
| FR-046–049 | stage-packet canonicalization/restart tests; PromptX adapter and broker tests; Subagents catalog/provenance tests; missing/dirty/incompatible submodule fixtures; runtime-image content assertions |
| FR-050–057 | kill/restart/reboot simulations; provider/quota waits; preservation failure tests |
| FR-060–062 | TUI/API snapshots; Hermes plugin contract tests; socket/listener assertions |
| FR-063–069 | clean Ubuntu 22.04/24.04 install and reinstall; interactive/unattended configuration; rootless boundary tests; management CLI authorization; signed stable/edge/pinned update and rollback; backup/restore/uninstall; release-document completeness |
| NFR-001 | `pytest tests/security -q` |
| NFR-002–003 | `pytest tests/recovery tests/integration -q`; installer second convergence and interrupted-operation recovery |
| NFR-004–005 | admission/resource fixtures and metrics assertions |
| NFR-006 | redaction corpus and retention dry run |
| NFR-007–008 | release manifest and documentation check; product-rename fixture; second-host installer scenario |
| NFR-009 | clean recursive clone; deterministic companion builds; upstream-change/pointer-update audit; coordinated upgrade and rollback fixture |

Release evidence also includes:

- `uv run ruff check .` and `uv run mypy src`;
- complete `uv run pytest`;
- installer lint and shell tests, Compose rendering validation, image scans, and
  clean-host appliance scenarios on Ubuntu 22.04 and 24.04;
- signed manifest, immutable-digest, SBOM, compatibility-matrix, and required
  release-document checks;
- clean-host encrypted restore drill;
- 14 consecutive days and at least 25 recorded tasks across two projects with no
  lost task/session correlation or unauthorized state change.
