---
title: Container-First Deployment Design
tags:
  - aegis
  - design
  - deployment
---

# Container-first deployment design

Status: accepted

Date: 2026-07-23

## 1. Outcome

Aegis ships as a rootless Docker Compose appliance. An operator installs,
configures, starts, inspects, upgrades, backs up, restores, and removes it through
one host-side management command without needing to understand its internal
containers.

The command name is `ae`. The design uses `<product-cli>` where generated
packaging must derive the value from one product metadata definition.

The initial host compatibility contract is:

- Ubuntu 22.04 LTS and Ubuntu 24.04 LTS;
- a clean VPS with systemd, cgroup v2, user namespaces, persistent storage, and
  outbound HTTPS;
- one installation-time `sudo` authorization;
- rootless, unprivileged operation after bootstrap.

The normal installation path is one command:

```bash
curl -fsSL https://releases.example.invalid/install.sh | sudo bash
```

The production release documentation must replace the example domain and include
a safer download, checksum/signature inspection, and local execution alternative.

## 2. Chosen approach

The appliance uses multiple containers behind one installation and management
interface. A monolithic container was rejected because it couples unrelated
process lifecycles, weakens isolation, and complicates health checks, upgrades,
and recovery. Host-native Ansible remains an optional fleet integration, not a
normal installation prerequisite.

The bootstrap installer:

1. verifies the host distribution, release, architecture, kernel features,
   storage, and network prerequisites;
2. verifies its own release metadata before making changes;
3. installs rootless Docker and the Compose plugin;
4. creates the locked `agentops` and `hermesops` service identities, private
   directories, subordinate UID/GID ranges, and required startup integration;
5. installs `<product-cli>` and a digest-pinned Compose bundle;
6. collects or imports configuration and secret references;
7. pulls immutable images, starts the appliance, and waits for readiness;
8. prints access, status, recovery, and documentation instructions.

Re-running the same installer is idempotent. It reconciles an incomplete
installation without duplicating identities, directories, services, or state.

## 3. Product naming

A single versioned product metadata file defines:

- display name;
- CLI command;
- package name;
- image registry namespace;
- Compose project names;
- default configuration and data directories;
- service labels;
- documentation variables.

Installers, release workflows, Compose templates, tests, and documentation derive
these values instead of embedding `Aegis` or `ae` independently.
Persistent internal identifiers remain stable when renaming them would orphan
volumes or break upgrades.

When an installed CLI is renamed, the next release installs the new command and a
compatibility alias for the previous name. The alias prints a deprecation warning
and remains for a documented support window.

## 4. Components and isolation

The appliance contains:

- the Aegis API, engine, policy, audit, and TUI container;
- the Herdr session-controller container;
- QMD and OpenViking knowledge containers;
- an optional Hermes ops gateway container;
- task-scoped worker and project-service containers created dynamically;
- the host bootstrap installer and `<product-cli>`;
- persistent configuration, state, artifact, knowledge, secret, and backup
  locations.

The installer preserves the two-account trust boundary:

- `agentops` owns the control plane, Herdr, knowledge services, worktrees,
  artifacts, and the rootless worker runtime;
- `hermesops` owns only the optional gateway and its isolated rootless container
  context;
- the gateway can reach the typed Aegis control socket but cannot access
  Herdr, worker-runtime sockets, worktrees, provider credentials, or the
  `agentops` container context.

Only the Aegis control-plane adapter can access the `agentops` rootless runtime
API. Worker, gateway, and knowledge containers never receive a Docker socket.
There is no rootful Docker socket, privileged container, host networking, device
mount, or unrestricted host path.

The Compose networks are private. Aegis, Herdr, QMD, and OpenViking publish no
public ports. Loopback bindings and Unix sockets are used where a container
boundary requires a host endpoint. Telegram uses outbound polling.

## 5. Configuration

Both installation modes produce the same versioned, schema-validated YAML
configuration:

- interactive mode is the default and guides a human through required values;
- unattended mode accepts a configuration file and documented environment
  overrides suitable for cloud-init, Terraform, CI, or fleet automation.

Environment variables are inputs only. The installer materializes the canonical
configuration, validates it, and records its nonsecret digest. Secrets are stored
separately in least-readable files or an approved secret provider. They never
appear in Compose YAML, image layers, command history, general environment
dumps, logs, support bundles, or release artifacts.

The management surface includes:

```text
<product-cli> config init
<product-cli> config edit
<product-cli> config validate
<product-cli> config diff
<product-cli> config apply
<product-cli> doctor
```

`config apply` validates before mutation, describes affected services, snapshots
the previous configuration, restarts only affected components, checks readiness,
and restores the prior configuration when safe application fails.

## 6. Container access and routine operations

Operators use `<product-cli>` instead of memorizing rootless Docker contexts,
Compose project names, paths, or user-runtime environment variables:

```text
<product-cli> status
<product-cli> ps
<product-cli> logs [service]
<product-cli> logs --follow [service]
<product-cli> shell <service>
<product-cli> exec <service> -- <command>
<product-cli> inspect <service>
<product-cli> restart [service]
```

Read-only status and log access may be delegated to the operator group. Shell,
execution, configuration, secret, update, backup, restore, and destructive
operations require elevated operator authorization and produce audit events.

Break-glass administrators may enter the exact service account and rootless
context through a documented command. This is not the normal operating path and
does not grant a worker or gateway access to the runtime API.

## 7. Releases and upgrades

Stable is the default signed release channel. Edge is an explicit opt-in channel
containing the newest commit that passed the edge release gate. Deployments never
follow a mutable `latest` tag.

The update interface includes:

```text
<product-cli> update --check
<product-cli> update --dry-run
<product-cli> update
<product-cli> update --version <version>
<product-cli> update --channel edge
<product-cli> rollback
<product-cli> version
```

An update:

1. fetches and verifies the signed channel manifest;
2. checks OS, architecture, Docker, Compose, schema, storage, migration, and
   downgrade compatibility;
3. presents the current and target versions and release notes;
4. creates and verifies a pre-upgrade backup;
5. pulls every image by immutable digest;
6. validates the candidate rendered Compose configuration;
7. replaces services in dependency order;
8. runs migrations and readiness checks;
9. records the installed manifest and image digests;
10. rolls back to the prior release automatically when the manifest declares
    rollback safe.

Automatic updates are opt-in. An unattended policy may define a maintenance
window, allowed channel, allowed version class, backup requirements, and failure
notification behavior.

Every published release includes:

- a signed release manifest and immutable image digests;
- the Compose bundle and configuration schemas;
- checksums, provenance, signatures, and a software bill of materials;
- installation, configuration, upgrade, migration, rollback, backup, restore,
  and troubleshooting documentation;
- a compatibility matrix;
- release notes, known issues, security changes, and backup implications.

Release automation refuses publication when required documentation, release
notes, compatibility evidence, migrations, rollback metadata, image signatures,
or release-required tests are absent.

## 8. Recovery and lifecycle

The management surface includes:

```text
<product-cli> doctor
<product-cli> repair
<product-cli> backup create
<product-cli> backup verify
<product-cli> restore <backup>
<product-cli> support-bundle
<product-cli> uninstall
```

`doctor` checks rootless Docker, user namespaces, disk space, permissions,
configuration, images, containers, private networking, volumes, sockets,
readiness, and database integrity. `repair` performs only bounded, documented
remediations and reports each change.

Backups are portable across supported hosts. They include operational state,
audit segments, configuration and flow snapshots, Herdr metadata, canonical
knowledge, required artifacts, sanitized archives, and non-rebuildable
OpenViking state. Rebuildable QMD indexes, images, worktrees, and disposable
project services are excluded. Secret backup requires an explicitly configured
encrypted destination.

Uninstall removes only the appliance's labeled containers and runtime resources
and preserves durable data by default. `--purge-data` requires resolved-path
validation and explicit confirmation. No lifecycle command performs global
Docker cleanup or touches unrelated resources.

Failures retain diagnostic evidence, identify the exact failed readiness or
integrity condition, and print a bounded recovery command. A running container is
not considered a successful installation or upgrade until its required health,
migration, and integration checks pass.

## 9. Verification

Release-required deployment tests cover:

- clean Ubuntu 22.04 and 24.04 installation;
- interactive and unattended installation;
- interrupted installation and repeated-install idempotency;
- rootless runtime, account, socket, network, mount, and secret boundaries;
- configuration validation, application, and rollback;
- operator authorization for container access;
- stable, edge, and pinned-version updates;
- interrupted downloads and upgrades;
- schema and database migrations;
- automatic rollback after failed readiness checks;
- backup verification, clean-host restore, and supported cross-host migration;
- VPS reboot and service-account runtime recovery;
- product rename and legacy CLI alias compatibility;
- uninstall with preservation and explicit purge;
- proof that unrelated Docker resources remain untouched;
- absence of unintended public listeners;
- complete and valid release documentation links and command examples.

CI builds multi-architecture images where all pinned dependencies support the
target architecture. Each supported architecture must pass the same security,
recovery, installation, and upgrade gates; otherwise the release manifest marks
it unsupported rather than publishing an unverified image.

## 10. Documentation and compatibility

The container-first installer is the primary supported deployment path. Optional
Ansible or infrastructure-as-code integrations call the same installer and
configuration contracts and must not fork deployment behavior.

The compatibility matrix is authoritative for:

- supported Ubuntu releases and CPU architectures;
- rootless Docker and Compose versions;
- release-channel and downgrade behavior;
- configuration, database, flow, and project schema transitions;
- backup restore compatibility;
- renamed commands and deprecation windows.

The first release supports Ubuntu 22.04 and 24.04. Additional distributions are
added only with an explicit compatibility contract and full release-gate
coverage.
