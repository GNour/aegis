---
title: Aegis Deployment
tags:
  - aegis
  - deployment
  - operations
---

# Aegis deployment (container-first)

Aegis ships as a rootless Docker Compose appliance managed through the `ae appliance`
command group. This is the primary supported deployment path; optional Ansible or
infrastructure-as-code integrations call the same installer and configuration contracts
and must not fork deployment behavior.

See the accepted
[[superpowers/specs/2026-07-23-container-first-deployment-design|container-first deployment design]]
and the [[plans/05-deployment-and-rollout|implementation plan]].

## Host compatibility (first release)

- Ubuntu 22.04 LTS and Ubuntu 24.04 LTS
- systemd, cgroup v2, user namespaces, persistent storage, outbound HTTPS
- one installation-time `sudo`; rootless and unprivileged after bootstrap

## Install

Normal path:

```bash
curl -fsSL https://releases.example.invalid/install.sh | sudo bash
```

Safer path (download, verify checksum/signature, inspect, then run):

```bash
curl -fsSLO https://releases.example.invalid/install.sh
curl -fsSLO https://releases.example.invalid/install.sh.sha256
sha256sum -c install.sh.sha256
less install.sh
sudo bash install.sh
```

> The production release replaces the example domain and publishes checksums, a detached
> signature, an SBOM, and a compatibility matrix. Deployments never follow a mutable
> `latest` tag — every image is pinned by digest via the signed release manifest.

## Configure

```bash
ae appliance config init > appliance.yaml   # write a starting configuration
ae appliance config validate --file appliance.yaml
ae appliance config diff --a old.yaml --b appliance.yaml
ae appliance config apply                   # validate, snapshot, restart affected services
```

Secrets are stored separately as references (file/env/provider) and never appear in the
configuration YAML, Compose files, images, logs, or support bundles. Private services
bind only loopback and publish no public ports; Telegram uses outbound polling.

## Operate

```bash
ae appliance status
ae appliance ps
ae appliance logs [service] [--follow]
ae appliance shell <service>          # elevated + audited
ae appliance exec <service>           # elevated + audited
ae appliance inspect <service>
ae appliance restart [service]        # elevated + audited
```

Read-only status and logs may be delegated to the operator group; shell, exec,
configuration, secret, update, backup, restore, and destructive operations require
elevated authorization and produce audit events.

## Update and roll back

```bash
ae appliance update --check
ae appliance update --dry-run
ae appliance update
ae appliance update --version <version>
ae appliance update --channel edge
ae appliance rollback
ae appliance version
```

An update verifies the signed channel manifest, checks compatibility, takes and verifies
a pre-upgrade backup, pulls every image by digest, validates the candidate Compose,
replaces services in dependency order, runs migrations and readiness checks, records the
installed manifest, and automatically rolls back when the manifest declares rollback safe.

## Recover and remove

```bash
ae appliance doctor
ae appliance repair
ae appliance backup create --source <data> --dest <archive>
ae appliance backup verify --archive <archive>
ae appliance restore <backup>
ae appliance support-bundle
ae appliance uninstall            # preserves durable data
ae appliance uninstall --purge-data   # requires explicit confirmation + path validation
```

Backups are portable across supported hosts and include durable state, audit segments,
config/flow snapshots, Herdr metadata, canonical knowledge, required artifacts, sanitized
archives, and non-rebuildable OpenViking state; rebuildable QMD indexes, images,
worktrees, and disposable services are excluded. Uninstall removes only the appliance's
labeled resources and never performs a global Docker prune.
