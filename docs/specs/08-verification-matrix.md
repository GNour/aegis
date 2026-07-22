# Verification matrix

Status: accepted test contract

| Requirement group | Primary verification |
|---|---|
| FR-001–006 | API contract tests; schema/linter/simulator/reload tests; snapshot fixture |
| FR-010–015 | SQLite transaction/idempotency tests; ledger chain and approval replay tests |
| FR-020–026 | worker capability tests; broker mocks; secret non-exposure and denial tests |
| FR-030–035 | worktree/service integration tests; traversal/symlink/label cleanup tests |
| FR-040–045 | skill fixture inspection; QMD ACL tests; context budget and RTK artifact tests |
| FR-050–057 | kill/restart/reboot simulations; provider/quota waits; preservation failure tests |
| FR-060–065 | TUI/API snapshots; Hermes plugin contract tests; socket/listener assertions |
| NFR-001 | `pytest tests/security -q` |
| NFR-002–003 | `pytest tests/recovery tests/integration -q`; Ansible second convergence |
| NFR-004–005 | admission/resource fixtures and metrics assertions |
| NFR-006 | redaction corpus and retention dry run |
| NFR-007–008 | release manifest check and second-inventory Molecule scenario |

Release evidence also includes:

- `uv run ruff check .` and `uv run mypy src`;
- complete `uv run pytest`;
- `make lint`, `make check`, and `make molecule` under `deploy/ansible`;
- clean-host encrypted restore drill;
- 14 consecutive days and at least 25 recorded tasks across two projects with no
  lost task/session correlation or unauthorized state change.
