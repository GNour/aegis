---
title: Flows, Routing, and Policy Specification
tags:
  - aegis
  - specification
  - policy
---

# Flows, routing, and policy specification

Status: accepted

## 1. Configuration packages

Configuration is versioned under `config/`:

```text
config/
|-- schemas/
|-- flows/
|-- routing.yaml
|-- stages/
|-- roles/
|-- capabilities/
`-- models.yaml
```

Every document has `api_version`, stable `id`, integer `version`, description,
and content-derived SHA-256 hash. References include required minimum versions.

## 2. Flow contract

A flow declares allowed callers, accepted intents, input schema, ordered stages,
non-removable gates, retry/fallback rules, and completion policy. A stage reference
resolves to a registered stage declaring:

- purpose, preconditions, and completion evidence;
- role, model alias, exact skill versions, and capability profile;
- structured input/output models;
- task services and health requirements;
- time, token, context, cost, retry, and attempt budgets;
- decision, approval, fallback, resume, knowledge, artifact, and cleanup behavior.

Flow files cannot contain shell commands. Project commands exist only in a trusted,
snapshotted `.aegis/project.yaml` and execute through the sandbox adapter.

## 3. Routing

Deterministic rules evaluate in ascending priority and may inspect authenticated
principal, interface, project metadata, intent, risk markers, requested outcome,
resource pressure, and prior attempts. The first terminal match selects a flow;
non-terminal rules may add risk or required gates. A model may classify intent,
but cannot grant capabilities or override a deterministic denial.

Ambiguous ties, unmatched high-impact requests, and requested flow/policy
conflicts create a `DecisionRequest`. The routing explanation records evaluated
rule IDs and contains no hidden model chain-of-thought.

## 4. Policy evaluation

Policy inputs are actor, task, project, stage, action type, canonical parameters,
requested capability, sandbox facts, and prior approvals. Outcomes are:

- `allow_autonomous`;
- `allow_brokered`;
- `require_decision`;
- `require_approval`;
- `deny_nondelegable`.

`deny_nondelegable` still creates an operator-visible escalation. Approval may
authorize a brokered equivalent but cannot change the denied raw operation into a
worker capability.

## 5. Reload and compatibility

`ae config validate` parses all files, rejects unknown fields/references and
cycles, compiles the catalog, and runs policy fixtures. `ae flow simulate`
accepts a fixture request and prints routing, stages, gates, capabilities, and
budgets without creating state. `ae config reload` builds a complete new
catalog and swaps it atomically only after validation succeeds.

Active tasks always use stored snapshots. Removed model aliases or runtime
adapters cannot strand a task: resume either uses the snapshot-compatible adapter
or enters `recovery_required` for an operator-selected migration.
