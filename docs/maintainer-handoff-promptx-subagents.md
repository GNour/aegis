# PromptX and Subagents maintainer handoff

Status: requested upstream work

Date: 2026-07-24

Audience: PromptX, Subagents, and Harness maintainers

## Shared ownership and workflow

PromptX and Subagents are required first-party companion packages for Harness.
They are not passive third-party dependencies. The Harness maintainers will
maintain and enhance both repositories through their normal branch, review,
release, and changelog processes.

Harness tracks each repository as a pinned Git submodule:

| Package | Harness path | Upstream |
|---|---|---|
| PromptX | `packages/promptx` | `https://github.com/GNour/promptx.git` |
| Subagents | `packages/subagents` | `https://github.com/GNour/subagents.git` |

For every companion change:

1. branch in the companion repository; never develop directly on `main`;
2. add package-local tests and release notes;
3. merge or accept the companion commit in its own repository;
4. update the Harness submodule pointer separately;
5. run Harness compatibility and security gates;
6. record source and built-artifact digests in the Harness release.

Harness must never depend on dirty submodule state or unpublished local commits.

## PromptX required changes

### P0 — required for Harness runtime admission

1. Publish a versioned runtime package from the repository and expose
   machine-readable `package_version` and `protocol_version` values.
2. Add a strict JSON request/response contract intended for control-plane use.
   Reject unknown fields and include an explicit schema version.
3. Accept injected, already-sanitized project facts with source digests. Provide
   a mode that disables all PromptX filesystem and Git discovery.
4. Separate deterministic enrichment from optional provider refinement in the
   contract. A deterministic result must remain available when the provider
   fails.
5. Support a fixed loopback broker endpoint and scoped proxy credential without
   requiring an upstream provider key. Reject non-allowlisted or redirected
   endpoints in brokered mode.
6. Bound every returned string, list, diagnostic, and total response size.
   Structured validation must reject rather than strip unknown keys.
7. Return typed failure/degradation codes. Do not hide malformed input, protocol
   failure, or security rejection behind an indistinguishable exit-zero pass.
8. Expose safe diagnostics containing gate verdict, reason, task class, quality,
   fact digests, provider/degraded state, duration, and token usage without
   content or credentials.

### P0 — security corrections

1. Redact and bound Git branch names and commit subjects before rendering or
   provider submission.
2. Enforce the remaining total context budget before adding each fact; one file
   must not overshoot the total cap.
3. Add semantic and size constraints to provider output, including objective,
   execution, constraints, deliverables, validation, completion criteria,
   assumptions, and unknowns.
4. Document that the user prompt leaves the host when provider refinement is
   enabled and expose a policy flag that can prohibit this path.
5. Ensure errors never include endpoint response bodies, proxy credentials,
   injected facts, or original prompt content.

### P1 — release and compatibility

1. Produce deterministic build artifacts with checksums, license metadata, SBOM,
   and changelog.
2. Add Linux and Windows CI for formatting, lint, type checking, unit,
   integration, adapter, security, and offline evaluation suites.
3. Publish a protocol compatibility table and a deprecation window for breaking
   changes.
4. Add a recorded-contract fixture set that Harness can consume without network
   access.
5. Keep Claude/Codex hook installers optional; Harness must not need them.

## Subagents required changes

### P0 — required for Harness catalog compilation

1. Publish a versioned, data-oriented catalog package with machine-readable
   `package_version` and `catalog_schema_version`.
2. Publish a JSON Schema for the catalog and reject unknown fields.
3. Export complete role data: stable ID, name, department, title, description,
   expertise, invocation procedure, standards, model hint, advisory tool profile,
   exact skill references, and handoffs.
4. Mark model, tool, skill, and handoff fields explicitly as advisory. They must
   not imply runtime authority.
5. Make generation deterministic and provide a `generate --check` command that
   fails when committed artifacts differ.
6. Emit a provenance manifest containing source commit, generator version,
   catalog digest, and every skill's source, exact version/commit, checksum, and
   license.
7. Reject unresolved handoffs, duplicate IDs, cyclic required handoffs, missing
   skill provenance, mutable versions, and unknown catalog kinds.
8. Provide a package-local validation command and recorded valid/malicious
   fixtures for Harness contract tests.

### P0 — installer and supply-chain corrections

1. Do not install registry skills from mutable `latest` references.
2. Fail the operation when required skill installation fails; do not continue
   with an incomplete catalog.
3. Replace destructive destination deletion with staged, atomic replacement,
   backup, and rollback.
4. Detect actual installed harnesses rather than treating every supported harness
   as detected.
5. Preserve or explicitly report every field lost by cross-harness conversion.
6. Keep installer behavior separate from the data package so Harness can consume
   the catalog without running installation code.

### P1 — release and compatibility

1. Add locked development dependencies, automated tests, and CI.
2. Test role uniqueness, department membership, handoff resolution, deterministic
   generation, schema validation, conversion fidelity, and installer rollback.
3. Publish checksums, license metadata, SBOM, changelog, and a catalog
   compatibility table.
4. Version role removals and renames with migration aliases so persisted Harness
   stage snapshots remain explainable.

## Harness-owned work

The companion maintainers do not need to implement Harness authority:

- Harness maps advisory role metadata to approved model aliases, exact skills,
  typed tools, and capability profiles.
- Harness owns flow selection, stage transitions, approvals, broker
  capabilities, worker isolation, context budgets, persistence, audit, recovery,
  knowledge preservation, and cleanup.
- Harness owns `StageExecutionPacket`, the PromptX adapter, the Subagents catalog
  compiler, integration tests, release provenance, and coordinated rollback.

The complete consuming contract is
[Stage packets and companion packages](specs/10-stage-packets-and-companion-packages.md).
