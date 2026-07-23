# AGENTS.md — Aegis

## Scope

This repository is the sole home of Aegis documentation, specifications,
plans, code, tests, Hermes integrations, configuration schemas, and reusable
deployment automation.

## Source of truth

Read in this order:

1. `docs/architecture.md`
2. `docs/specs/00-product-requirements.md`
3. the relevant subsystem specification under `docs/specs/`
4. the active plan under `docs/plans/`
5. accepted decisions under `docs/adrs/` and research under `docs/rfcs/`

If code and documentation conflict, stop and update both in the same change.

## Hard rules

1. Never commit secrets, credentials, IP addresses, provider tokens, Telegram
   tokens, subscription session data, unredacted transcripts, or production data.
2. Workers never receive raw provider, Git, Coolify, deployment, SSH, or
   infrastructure credentials. Use typed, scoped, revocable broker capabilities.
3. No arbitrary command endpoint. Flows reference registered stages and
   capabilities; project commands execute only inside the approved task sandbox.
4. `dev` is not an Aegis service account. Deploy the ops gateway as `hermesops`
   and the control/worker plane as `agentops`.
5. No sudo, rootful Docker socket, privileged container, host networking, device
   mount, or unrestricted host path for workers.
6. Every state transition is transactional, idempotent, and audit-recorded.
7. Knowledge and required artifacts must be committed and indexed before cleanup.
8. Every role gets only its declared skills and tools. Never mount a global skill
   catalog or global QMD MCP into workers.
9. Branch and PR; never develop directly on `main`. Commit format:
   `type(scope): subject`.
10. Use TDD for behavior. Negative security tests and restart/recovery tests are
    release gates, not optional coverage.

## Toolchain

- Python 3.12
- `uv` for environments, locking, and commands
- Pydantic v2 for contracts
- SQLite WAL for operational state
- JSONL plus SHA-256 chaining for the audit ledger
- FastAPI/Uvicorn on a Unix-domain socket for the typed local API
- Textual for the operator TUI
- pytest, Hypothesis, Ruff, and mypy for verification
- Ansible for reusable deployment automation

## Required verification

```bash
uv run ruff check .
uv run mypy src
uv run pytest
uv run pytest tests/security tests/recovery
cd deploy/ansible && make lint && make molecule
```

Run only the commands relevant to a documentation-only change, but always run a
local-link check and `git diff --check` before committing documentation.
