# VPS Refined integration contract

## Ownership

This repository owns Harness. The sibling `VPS Refined` infrastructure repository
owns the host baseline, Coolify, VPS-wide firewall policy, shared backups, and the
instance inventory. It consumes a pinned Harness release and may carry a short
integration pointer, but it must not duplicate Harness source or detailed specs.

## Required host inputs

The infrastructure repository supplies variables for:

- `harness_gateway_user` (`hermesops` for the current instance);
- `harness_orchestrator_user` (`agentops` for the current instance);
- allowed operator Unix group and Telegram user IDs;
- state, artifact, worktree, company-brain, and backup paths;
- pinned Harness release/checksum and dependency versions;
- loopback ports and Unix-socket paths;
- rootless runtime storage and resource ceilings;
- encrypted secret references, never plaintext values.

## Harness outputs

The reusable Ansible content under `deploy/ansible/` creates the two service
accounts, installs the pinned package, configures user services and sockets,
creates private directories, installs rootless worker prerequisites, and registers
backup paths. The infrastructure repository invokes that content after base host
hardening.

## Current-instance invariants

- `dev` remains the owner's interactive account and keeps its current role during
  the pilot.
- Coolify remains publicly accessible through
  `https://coolify.nco-tech.com` on HTTPS/443 with Coolify authentication.
- Harness does not require public access to Coolify's raw `:8000` listener.
- Harness, Herdr, QMD, and OpenViking have no public listener.
- The removed Multica server has no migration phase; only verified stale daemon,
  CLI, and state remnants are eligible for scoped cleanup.
- Existing Hermes units are stabilized before Telegram rollout; obsolete
  `--foreground` flags are removed only after checking the installed Hermes CLI.

## Release handshake

1. Harness CI publishes an immutable version and checksum.
2. The infrastructure repository updates its pinned version in a branch.
3. Ansible check mode, lint, and Molecule pass.
4. A staging installation runs the Harness smoke and recovery suites.
5. The operator approves the VPS deployment.
6. The deployment records the Harness version in the host audit inventory.
