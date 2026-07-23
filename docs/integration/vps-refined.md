# VPS Refined integration contract

## Ownership

This repository owns Aegis. The sibling `VPS Refined` infrastructure repository
owns the host baseline, Coolify, VPS-wide firewall policy, shared backups, and the
instance inventory. It consumes a pinned Aegis release and may carry a short
integration pointer, but it must not duplicate Aegis source or detailed specs.

## Required host inputs

The infrastructure repository supplies variables for:

- `aegis_gateway_user` (`hermesops` for the current instance);
- `aegis_orchestrator_user` (`agentops` for the current instance);
- allowed operator Unix group and Telegram user IDs;
- state, artifact, worktree, company-brain, and backup paths;
- pinned Aegis release/checksum and dependency versions;
- loopback ports and Unix-socket paths;
- rootless runtime storage and resource ceilings;
- encrypted secret references, never plaintext values.

## Aegis outputs

The signed container-first release supplies an idempotent Ubuntu bootstrap, the
renameable management CLI, rootless Compose bundles, image digests,
configuration schemas, compatibility metadata, and backup hooks. The bootstrap
creates the two service accounts, installs rootless Docker and Compose, configures
startup and sockets, creates private directories, and starts the pinned
appliance.

The infrastructure repository invokes the unattended installer after base host
hardening. Optional Ansible content is a thin wrapper over the same installer and
configuration contract; it must not implement a divergent deployment path.

## Current-instance invariants

- `dev` remains the owner's interactive account and keeps its current role during
  the pilot.
- Coolify remains publicly accessible through
  `https://coolify.nco-tech.com` on HTTPS/443 with Coolify authentication.
- Aegis does not require public access to Coolify's raw `:8000` listener.
- Aegis, Herdr, QMD, and OpenViking have no public listener.
- The removed Multica server has no migration phase; only verified stale daemon,
  CLI, and state remnants are eligible for scoped cleanup.
- Existing Hermes units are stabilized before Telegram rollout; obsolete
  `--foreground` flags are removed only after checking the installed Hermes CLI.

## Release handshake

1. Aegis CI publishes signed immutable images, a release manifest, the Compose
   bundle, checksums, and required release documentation.
2. The infrastructure repository updates its pinned version in a branch.
3. The unattended installer dry-run and configuration validation pass.
4. A clean supported staging host runs install, idempotency, smoke, upgrade,
   rollback, backup/restore, and recovery suites.
5. The operator approves the VPS deployment.
6. The deployment records the Aegis version, release-manifest digest, image
   digests, configuration digest, and backup receipt in the host audit inventory.
