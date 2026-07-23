# 0003 — Give workers autonomy through capability brokers
Status: accepted
Date: 2026-07-23

## Context

Workers should read/write, build, test, review, and document freely inside their
assigned worktree. They must not receive raw provider, Git, Coolify, deployment,
or infrastructure keys and must escalate decisions or exceptional risk. Merely
prompting an agent not to read an environment variable is not a security boundary.

## Decision

We will allow routine worktree operations autonomously inside a rootless,
task-scoped runtime. External effects and secret-dependent operations go through
typed Aegis adapters. Workers receive revocable task capabilities rather than
long-lived upstream credentials. Human approval signs one exact action when a
flow or policy requires judgment. Nondelegable actions may be performed by the
broker or human after escalation, but approval never exposes a raw secret or
unrestricted host access to the worker.

## Consequences

Agents can iterate without approval fatigue while credentials and host authority
stay outside their sandbox. Aegis must build a credential/model proxy, strict
path and network policy, one-use approvals, revocation, redaction, and negative
tests. Some actions that CLIs normally perform directly must instead use adapters.

## Alternatives rejected

- Ask for every read/write/test action — safe but destroys useful autonomy.
- Put scoped long-lived keys in worker environments — simpler, but an agent can
  inspect or exfiltrate them through its own shell tools.
