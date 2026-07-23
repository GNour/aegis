# 0002 — Use versioned declarative Aegis flows
Status: accepted
Date: 2026-07-23

## Context

The owner needs to change task pipelines easily and later let Hermes select
different flows from natural-language requests and deterministic rules. A hard-
coded pipeline would require code deployments for routine process changes, while
free-form agent-generated workflows could introduce arbitrary capabilities.

## Decision

We will define flows, stages, routing rules, role profiles, model aliases,
capability profiles, budgets, and per-role skills as versioned configuration.
Flows reference only registered stages and capabilities and cannot embed arbitrary
host commands. Aegis validates, lints, simulates, and atomically reloads them.
Each task snapshots the exact flow version and content hash at creation.

## Consequences

New or revised workflows become reviewable data changes. Hermes can propose or
request a flow, but server-side routing and policy remain authoritative. Aegis
must maintain schemas, migrations, compatibility rules, generated documentation,
and simulation fixtures. Active tasks remain stable when definitions change.

## Alternatives rejected

- One hard-coded lifecycle — safe but cannot evolve without code changes.
- Agent-authored executable workflows — flexible but breaks capability review and
  makes auditing and reproduction unreliable.
