# 0001 — Isolate the Harness gateway and worker plane
Status: accepted
Date: 2026-07-23

## Context

The existing `dev` account combines interactive subscription logins, project
workspaces, Docker-group membership, and the ops Hermes gateway. Docker-group
membership is root-equivalent, while the Harness
[execution specification](../specs/03-execution-and-isolation.md) requires
capability and secret isolation. The owner wants `dev` preserved during the pilot.

## Decision

We will keep `dev` as the owner's interactive account and create two locked,
non-SSH service accounts: `hermesops` for the private Telegram gateway and
`agentops` for Harness, Herdr, worktrees, rootless workers, QMD, and OpenViking.
Hermes may call only the Harness control socket. It cannot access the Herdr socket,
worktrees, rootful Docker, runtime credentials, or host commands.

## Consequences

Compromise of the conversational gateway does not directly expose agent terminals
or code workspaces. Secrets and backups gain two owners and Ansible must manage
additional homes, sockets, service units, and linger. Installation and device
login flows must be performed through `deploy` with `sudo -u` because the service
accounts have no direct SSH login.

## Alternatives rejected

- Repurpose `dev` as the company runtime — preserves existing logins but keeps a
  chat gateway in a root-equivalent account.
- Run gateway and workers under one new user — simpler, but lets a compromised
  gateway reach Herdr and worker state through same-user permissions.
