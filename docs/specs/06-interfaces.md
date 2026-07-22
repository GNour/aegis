# TUI and Hermes interface specification

Status: accepted

## 1. Shared behavior

Both clients use the same versioned control API. They do not implement local
authorization shortcuts or state transitions. Every mutation displays/returns the
task ID, resulting state, and audit correlation ID.

## 2. Textual TUI

The TUI provides:

- task creation with explicit/auto flow selection and routing preview;
- task list filters for project, state, flow, risk, and attention required;
- task detail with stage timeline, attempts, decisions, approvals, sessions,
  services, budgets, artifacts, and knowledge receipts;
- exact approval and rejection views showing action digest, scope, risk, expiry,
  evidence, and effect;
- pause/resume/cancel actions;
- safe attachment to an approved Herdr session in a separate terminal;
- config catalog, validation, and simulation output;
- audit-chain and recovery status.

The TUI never renders secret-bearing raw environment data. Full logs open only
through an artifact accessor that applies authorization and redaction.

## 3. Hermes plugin

The `company-control` plugin exposes exactly the nine FR-001 functions. It maps an
allowlisted Telegram numeric user ID to a Harness actor, creates a signed principal
assertion, validates arguments before transport, and renders bounded structured
responses. It has no shell, Herdr, worktree, provider-key, or Docker access.

Approval messages include a stable short request ID and summary. Natural-language
"yes" is insufficient when more than one approval is pending; Hermes asks the
operator to identify the request. The plugin sends the exact server-provided action
digest back to Harness.

## 4. Hermes skill

The `company-orchestrator` skill teaches Hermes to clarify intent, call
`list_flows`, explain the server routing result, create tasks, surface decisions,
report status, and handle resume/cancel/note/reminder operations. It explicitly
states that skill text grants no capability and that prohibited requests are
escalated, not translated into commands.

## 5. Notifications

Harness emits bounded attention events for decision/approval requests, quota reset,
provider recovery, failed preservation, cleanup quarantine, and task completion.
The Hermes gateway may deliver them to allowlisted chats. Notification delivery is
idempotent and records message ID and result; failure never changes task state.
