# Recovery, audit, and cleanup specification

Status: accepted

## 1. Failure classification

| Class | Required state and behavior |
|---|---|
| Process exit/kill | inspect runtime/session, resume or handoff replacement |
| Harness/Herdr restart | startup reconciliation before new admission |
| VPS reboot | restore services, reconcile, then resume eligible tasks |
| Credit/quota limit | `waiting_quota`, provider/model, reset/retry time, no loop |
| Provider outage | `waiting_provider`, bounded backoff and circuit breaker |
| Human decision | `waiting_human`, exact question/evidence/options |
| Policy denial | `blocked`, denied action and safe alternatives |
| State/resource mismatch | `recovery_required`, quarantine uncertain resources |

## 2. Handoffs and resume

A handoff is valid only when its schema passes, referenced commit exists, changed
file list matches Git, test evidence artifacts exist, and its digest is recorded.
Resume attempts the native runtime session first. If unavailable, a new attempt
receives the latest validated handoff plus bounded current context. A replacement
cannot inherit broader skills, network, mounts, credentials, or capabilities.

## 3. Startup reconciliation

The sweeper compares nonterminal database records with Herdr sessions, worktrees,
rootless containers/networks/volumes, port leases, and knowledge jobs. It adopts
only resources whose immutable labels and nonces match the task record. Unknown or
conflicting resources are quarantined and surfaced; they are never automatically
deleted.

Reconciliation and cleanup operations use leases and idempotency records so only
one service instance acts on a task at a time.

## 4. Audit integrity and redaction

Events are canonical JSON with sorted keys and no insignificant whitespace. The
event hash is SHA-256 over version, sequence, prior hash, and redacted payload.
Redaction happens before persistence and covers configured secret names, token
formats, authorization headers, credential paths, and runtime-provided sensitive
fields. A verification command recomputes the chain and reports the first mismatch.

Ledger rotation starts a new segment with the prior segment's terminal hash and a
signed segment manifest. Rotation never rewrites an existing event.

## 5. Cleanup preconditions

Cleanup requires frozen writes, final deterministic verification, completed
review, valid handoff, artifact digests, canonical knowledge commit, QMD receipt,
OpenViking receipt, and no unresolved mandatory decision. Cancellation follows the
same preservation requirements unless the operator selects a documented emergency
quarantine path.

Cleanup stops exact task-labeled containers, removes exact task networks and
disposable volumes, releases ports, removes the worktree through Git, and verifies
absence. It never deletes shared caches, repositories, volumes, or unlabeled
resources and never invokes global prune.

## 6. Retention and backup

Task/session identifiers, decisions, approvals, handoffs, canonical Markdown, and
Git history are indefinite. Sanitized exports default to 180 days. Complete logs
follow artifact policy. SQLite, JSONL, flow snapshots, Herdr metadata, company
brain, sanitized archives, and non-rebuildable OpenViking state are backed up;
QMD indexes are rebuilt.
