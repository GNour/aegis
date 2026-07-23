# Domain and control API specification

Status: accepted

## 1. Identifiers and time

IDs are UUIDv7 strings. Stored timestamps are UTC RFC 3339 with microseconds.
Every mutation carries `actor_id`, `principal_type`, `correlation_id`,
`causation_id`, and an idempotency key.

## 2. Authoritative records

| Record | Required content |
|---|---|
| `TaskManifest` | ID, project, request, acceptance criteria, risk, state, flow snapshot, source interface, creator, budgets, base commit, branch, worktree, timestamps |
| `FlowRun` | task, flow ID/version/hash, routing reason, status, current stage |
| `StageRun` | stage snapshot, role/model/skills/capabilities, status, budgets, ordinal |
| `Attempt` | runtime, native session ID, Herdr ID, start/end, exit/failure class, tokens/cost |
| `DecisionRequest` | question, options, evidence, impact, requester, resolution |
| `ApprovalRequest` | canonical action payload hash, scope, risk, reason, expiry, nonce, signer, use event |
| `SessionLink` | task/stage/attempt, runtime, native ID, Herdr ID, sanitized export artifact |
| `HandoffPacket` | outcome, files, commits, tests, decisions, risks, unresolved questions, next action |
| `ArtifactRecord` | type, URI/path, digest, size, redaction class, retention, producer |
| `KnowledgeSync` | canonical commit, QMD collection/receipt, OpenViking URI/receipt, status |
| `CleanupRecord` | labeled targets, preconditions, actions, verification, failure/recovery state |
| `AuditEvent` | sequence, event ID/type/version, actor, task, payload, prior hash, event hash |

Pydantic models reject unknown fields at API and config boundaries. Database
rows carry an integer schema version and migrations are forward-only.

## 3. Task state machine

Normal path:

```text
intake -> clarify -> planned -> ready -> executing -> verifying -> reviewing
       -> preserving -> cleaning -> complete
```

Wait states are `waiting_human`, `waiting_quota`, `waiting_provider`,
`retry_scheduled`, `blocked`, and `recovery_required`. Terminal states are
`complete`, `cancelled`, and `failed`.

Transitions are allowlisted. Each mutation starts one SQLite transaction, checks
expected state/version and idempotency key, updates operational rows, inserts an
outbox audit event, and commits. A ledger flusher appends outbox events in sequence
and marks them flushed; startup completes any committed but unflushed events.

## 4. API transport and identity

The versioned HTTP API is served through `/run/aegis/control.sock`. Filesystem
ownership/mode is the first boundary. Every request also carries a short-lived
signed principal assertion containing actor, interface, allowed operation, issue
time, expiry, nonce, and request-body digest.

- The TUI obtains an operator assertion from the local operator credential file.
- The Hermes plugin signs only allowlisted Telegram identities and operations.
- Aegis validates signature, expiry, nonce replay, operation, and body digest.
- Assertions are redacted from logs and never forwarded to workers.

## 5. Operations

All responses use `{data, meta}` on success and `{error, meta}` on failure.
`meta` includes request, correlation, and server-version IDs.

| Operation | Input | Output |
|---|---|---|
| `GET /v1/flows` | optional project/intent | allowed flow catalog and input schema |
| `POST /v1/tasks` | project, request, criteria, flow ID or `auto`, risk hints | task manifest, routing decision, next state |
| `GET /v1/tasks/{id}` | include flags | current state, stage, waits, decisions, sessions, artifacts |
| `POST /v1/approvals/{id}:approve` | action digest, expiry, operator comment | single-use approval result |
| `POST /v1/approvals/{id}:reject` | reason | rejection and task transition |
| `POST /v1/tasks/{id}:cancel` | reason, cleanup mode | cancellation receipt and preservation state |
| `POST /v1/tasks/{id}:resume` | expected state/version, reason | resume decision and dispatch state |
| `POST /v1/notes` | project/task, Markdown text, source metadata | canonical inbox proposal ID |
| `POST /v1/reminders` | message, schedule, timezone | normalized schedule and reminder ID |

Mutation requests require an `Idempotency-Key`. Repeating a key with the same
body returns the original result; reusing it with a different body returns 409.

## 6. Error contract

Stable codes include `validation_failed`, `unauthorized`, `forbidden`,
`not_found`, `state_conflict`, `idempotency_conflict`, `approval_expired`,
`approval_replayed`, `policy_denied`, `resource_exhausted`, `provider_wait`, and
`recovery_required`. Human-readable messages contain no secret values or raw
command output.
