# Deployment and operations specification

Status: accepted

## 1. Accounts and paths

`hermesops` and `agentops` have locked passwords, private `0700` homes, no SSH
authorized keys, no sudo, and no rootful Docker group. `hermesops` owns its Hermes
configuration and the client assertion key. `agentops` owns Harness, Herdr,
rootless runtime state, QMD, OpenViking, worktrees, artifacts, and company-brain.

System paths are variable-driven. Defaults use `/etc/harness` for nonsecret config,
`/var/lib/harness` for durable state, `/var/lib/harness-worktrees` for task roots,
`/var/lib/harness-artifacts` for protected artifacts, and `/run/harness` for
sockets. Ownership and modes are explicit.

## 2. Services

Hardened systemd units cover Harness API/engine, Herdr, OpenViking, Hermes ops, and
scheduled reconciliation/retention jobs. Units set `NoNewPrivileges`, private
temporary directories, restrictive umask, explicit writable paths, bounded
resources, restart policies without rapid loops, and dependency/readiness checks.

Installed CLI flags are verified during deployment; unsupported flags fail
preflight instead of entering restart loops.

## 3. Exposure

Harness and Herdr use Unix sockets. OpenViking and optional QMD HTTP bind loopback.
There is no Traefik/Coolify route for internal control services. Telegram uses
outbound polling. Coolify's public HTTPS dashboard is an independent VPS service.

## 4. Secrets

Deployment accepts encrypted Ansible Vault/SOPS references and creates per-service
runtime files with least ownership. Logs use `no_log` for materialization. Workers
receive no long-lived secret file. Rotation supports overlap for client assertion
keys and revokes task model capabilities immediately.

## 5. Backups and restore

Backups include state database, audit segments, config/flow snapshots, session
metadata, canonical brain, sanitized archives, and required OpenViking state.
Restore into a clean host verifies audit chain, schema migrations, state inventory,
Git repositories, OpenViking rebuild/readiness, and nonterminal task recovery before
the Telegram gateway is enabled.

## 6. Rollout gates

Order is stabilization, accounts, core state/API, flow/policy, isolated execution,
knowledge, TUI, Telegram, then soak. Pilot admission remains two workers. Telegram
waits until local TUI security/recovery acceptance passes. Broader external-effect
automation waits until the 14-day/25-task/two-project soak passes.
