# Execution and isolation specification

Status: accepted

## 1. Trust boundary

Harness and Herdr run as `agentops`. Workers run in task-scoped rootless
containers with a filtered environment, read-only base filesystem, writable
worktree and task temp paths, dropped Linux capabilities, `no-new-privileges`,
PID/memory/CPU limits, and network disabled unless the stage declares an approved
egress profile.

Herdr's socket, Harness state, other projects, other worktrees, company-brain
write credentials, host home directories, and all raw secrets are absent from the
worker mount namespace.

## 2. Worktree lifecycle

1. Resolve project from the operator-managed project registry.
2. Fetch through the Git broker when policy allows; workers have no remote token.
3. Verify a clean trusted base commit and read its project manifest.
4. Create `task/<task-id>-<slug>` and a worktree under the configured task root.
5. Snapshot repository, manifest, branch, and base commit into `TaskManifest`.
6. Start services and worker; keep them through verification/review.
7. Freeze writes, preserve evidence, then remove exact labeled resources and
   worktree after knowledge gates pass.

## 3. Project manifest

`.harness/project.yaml` declares named commands, services, fixtures, artifacts,
and limits. Command entries are argument arrays, not shell strings. The schema
rejects interpolation, host paths, privileged flags, devices, unbounded resource
values, production fixture markers, and unknown service keys.

The manifest is read from the base commit before worker writes. Changes made by a
worker affect a future task only after human review and merge.

## 4. Rootless services

Every task receives an immutable label set containing Harness instance, project,
task, flow run, and creation nonce. Compose project name, network, volumes, and
ports derive from the task ID. Ports are allocated transactionally from a
configured loopback range and released only after cleanup verification.

Health checks have bounded retries and logs. Failed setup enters a classified
wait/failure state; it does not silently broaden networking or privileges.

## 5. Runtime adapters

Each runtime adapter implements `start`, `inspect`, `send_control`, `interrupt`,
`resume`, `export_sanitized`, `usage`, and `close`. Herdr is the only process
controller. Harness records both Herdr and native runtime IDs.

OpenCode is blocked until the model-proxy acceptance test proves the upstream key
is absent from environment, files, process inspection, session export, command
output, and artifacts. Codex writing mode is blocked until subscription-session
mounts cannot be reached by task code. Read-only use follows the same containment
tests.

## 6. Git and external effects

Workers may create local commits. Push, PR creation, merge, deployment, database
migration, secret-dependent operation, and infrastructure mutation use typed
brokers. Broker requests include exact repository/project, ref, digest, action,
risk, and approval reference. Brokers validate the task's recorded output before
performing an effect and return a redacted receipt.
