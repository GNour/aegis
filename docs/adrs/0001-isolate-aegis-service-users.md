---
title: Isolate the Aegis Gateway and Worker Plane
tags:
  - aegis
  - adr
  - security
---

# 0001 — Isolate the Aegis gateway and worker plane
Status: accepted
Date: 2026-07-23

## Context

The existing `dev` account combines interactive subscription logins, project
workspaces, Docker-group membership, and the ops Hermes gateway. Docker-group
membership is root-equivalent, while the Aegis
[[specs/03-execution-and-isolation|execution specification]] requires
capability and secret isolation. The owner wants `dev` preserved during the pilot.

## Decision

We will keep `dev` as the owner's interactive account and create two locked,
non-SSH service accounts: `hermesops` for the private Telegram gateway and
`agentops` for Aegis, Herdr, worktrees, rootless workers, QMD, and OpenViking.
Hermes may call only the Aegis control socket. It cannot access the Herdr socket,
worktrees, rootful Docker, runtime credentials, or host commands.

## Consequences

Compromise of the conversational gateway does not directly expose agent terminals
or code workspaces. Secrets and backups gain two owners, and the container-first
bootstrap plus optional fleet automation must manage additional homes, isolated
rootless contexts, sockets, startup integration, and linger. Installation and
device-login flows must be performed through `deploy` with `sudo -u` because the
service accounts have no direct SSH login.

## Alternatives rejected

- Repurpose `dev` as the company runtime — preserves existing logins but keeps a
  chat gateway in a root-equivalent account.
- Run gateway and workers under one new user — simpler, but lets a compromised
  gateway reach Herdr and worker state through same-user permissions.
