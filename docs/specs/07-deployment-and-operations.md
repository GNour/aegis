# Deployment and operations specification

Status: accepted

The detailed operator experience and component rationale are defined in the
[container-first deployment design](../superpowers/specs/2026-07-23-container-first-deployment-design.md).

## 1. Supported hosts and installation

The initial release supports clean Ubuntu 22.04 LTS and Ubuntu 24.04 LTS VPS
hosts. The bootstrap verifies systemd, cgroup v2, user namespaces, architecture,
storage, and outbound HTTPS before mutation.

Normal installation is one command. It may request `sudo` for host bootstrap,
but the installed appliance runs rootless and unprivileged. The installer
installs rootless Docker and Compose, service identities, private directories,
the product management CLI, the pinned Compose bundle, and startup integration.
It is idempotent and resumes safely after partial failure.

Interactive installation is the default. Unattended installation accepts the
same versioned YAML configuration plus documented environment inputs.

## 2. Product metadata and management CLI

The working CLI name is `harnessctl`, but it is not a permanent product
identifier. One product metadata definition drives display, command, package,
image namespace, Compose project, label, directory, test, and documentation
names. A rename preserves stable storage identifiers and installs a time-bounded
compatibility alias for the previous command.

The CLI owns installation status, configuration, container inspection, logs,
bounded shell/exec access, health diagnosis, update, rollback, backup, restore,
support-bundle generation, and uninstall. Operators do not need to construct
rootless Docker environment variables or Compose commands.

## 3. Accounts, runtimes, and paths

`hermesops` and `agentops` have locked passwords, private `0700` homes, no SSH
authorized keys, no sudo, and no rootful Docker group.

`agentops` owns Harness, Herdr, worktrees, artifacts, QMD, OpenViking, and the
rootless worker runtime. `hermesops` owns only its Hermes configuration, client
assertion key, and isolated rootless gateway context. It cannot reach the
`agentops` runtime API, Herdr, worktrees, or runtime credentials.

System paths are product-metadata- and variable-driven. Defaults use private
configuration, durable state, worktree, artifact, backup, and runtime-socket
roots with explicit ownership and modes.

## 4. Containers and startup

The rootless Compose appliance contains Harness, Herdr, QMD, OpenViking, and the
optional Hermes gateway. Task workers and project services are created
dynamically through the `agentops` rootless runtime.

Only the Harness runtime adapter can reach that runtime API. Workers, Hermes, and
knowledge services never receive a Docker socket. Containers may not use
privileged mode, host networking, devices, the rootful Docker socket, broad
capabilities, or unrestricted host paths.

Host startup integration starts the two rootless contexts in dependency order,
waits for readiness, and avoids restart loops. Unsupported installed CLI or
Compose behavior fails preflight rather than being rendered into startup
configuration.

## 5. Exposure and access

Harness and Herdr use Unix sockets. OpenViking and optional QMD HTTP bind
loopback or private container networks. No internal control component publishes a
public port. Telegram uses outbound polling. Coolify's public HTTPS dashboard is
independent of Harness.

Read-only status and logs may be delegated to the operator group. Shell, exec,
configuration, secret, update, backup, restore, and destructive operations
require elevated operator authorization and create audit events.

## 6. Configuration and secrets

One strict, versioned YAML schema is canonical for interactive and unattended
configuration. Applying configuration validates first, reports affected
services, snapshots the previous configuration, restarts only affected
components, checks readiness, and restores the previous version when safe
application fails.

Secrets are separate from configuration and Compose YAML. Installation accepts
encrypted references or protected input files and materializes least-readable,
per-service runtime files. Secret values never enter image layers, command
history, logs, support bundles, general environment dumps, or release artifacts.
Workers receive no long-lived secret file.

## 7. Releases, updates, and rollback

Stable is the default signed channel. Edge is explicit opt-in. A deployment
resolves a signed release manifest to immutable image digests and never follows a
mutable `latest` tag.

An update verifies compatibility and signatures, presents release notes, creates
and verifies a backup, pulls images, validates rendered Compose configuration,
replaces services in dependency order, runs migrations and readiness checks, and
records the exact installed manifest. It rolls back automatically only when the
release metadata declares rollback safe.

Automatic updates are opt-in and bounded by a configured maintenance window,
channel, version class, backup gate, and failure-notification policy.

Every release contains signed manifests, image digests, Compose and schema
bundles, checksums, provenance, an SBOM, a compatibility matrix, release notes,
known issues, and complete installation, configuration, migration, upgrade,
rollback, backup, restore, and troubleshooting documentation. Missing
documentation or rollback metadata blocks publication.

## 8. Backups, restore, and removal

Portable backups include the state database, audit segments, config/flow
snapshots, session metadata, canonical brain, sanitized archives, required
artifacts, and non-rebuildable OpenViking state. Rebuildable QMD indexes, image
layers, worktrees, and disposable services are excluded.

A clean-host restore verifies audit chains, database integrity and migrations,
state inventory, Git repositories, OpenViking rebuild/readiness, and nonterminal
task recovery before Telegram is enabled.

Uninstall removes only immutable product-labeled containers and runtime resources
and preserves durable data by default. Full purge requires resolved-path
validation and explicit confirmation. No operation performs a global Docker
prune or affects unrelated resources.

## 9. Rollout and compatibility gates

Order is bootstrap compatibility, accounts and rootless runtimes, core state/API,
flow/policy, isolated execution, knowledge, TUI, Telegram, then soak. Pilot
admission remains two workers. Telegram waits until local TUI security/recovery
acceptance passes. Broader external-effect automation waits until the
14-day/25-task/two-project soak passes.

Ubuntu 22.04 and 24.04 must each pass clean install, idempotent reinstall,
interactive and unattended configuration, reboot, update, rollback, backup,
clean-host restore, isolation, and uninstall tests. An architecture or
distribution is not published as supported until it passes the same gates.
