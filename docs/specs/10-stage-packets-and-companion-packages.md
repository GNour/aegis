# Stage packets and companion packages

Status: approved design

Date: 2026-07-24

## 1. Outcome

Harness uses PromptX and Subagents as required, actively maintained companion
packages without delegating orchestration, policy, state, audit, recovery, or
cleanup authority to either package.

- PromptX is a pinned runtime dependency of the Harness control plane.
- Subagents is a pinned build-time catalog dependency whose validated output is
  embedded in Harness releases.
- Both repositories are Git submodules under `packages/` and are maintained and
  enhanced alongside Harness.
- Workers receive neither companion repository, the Subagents installer, the
  global role/skill catalog, nor PromptX provider credentials.

## 2. Source and release ownership

The repository contains:

```text
packages/
|-- promptx/       # Git submodule: https://github.com/GNour/promptx.git
`-- subagents/     # Git submodule: https://github.com/GNour/subagents.git
```

The submodule commit recorded by Harness is the authoritative source pin.
`.gitmodules` uses HTTPS fetch URLs so clean CI and deployment builds do not
require developer SSH credentials. Maintainers may configure local SSH push URLs
without committing them.

Harness maintainers actively maintain and enhance both companion packages.
Changes follow this order:

1. create a non-`main` branch in the companion repository;
2. implement and verify the companion change in that repository;
3. merge or otherwise accept the companion change with its own release history;
4. update the Harness submodule pointer in a separate branch and commit;
5. run compatibility, security, recovery, packaging, and rollback gates;
6. publish Harness artifacts containing the recorded source and artifact digests.

A Harness commit never records dirty submodule content. A submodule pointer update
never substitutes for an upstream commit or release note.

## 3. Stage execution packet

`StageExecutionPacket` is the immutable input to worker dispatch. It contains:

- task, flow, stage, role, model, skill, capability, and project-manifest
  snapshots;
- the original request digest and bounded PromptX enrichment;
- the exact context envelope and source digests;
- generated tool definitions and broker capability references;
- time, token, context, cost, retry, and attempt budgets;
- completion evidence, artifact, decision, approval, and handoff requirements;
- PromptX source commit, package version, protocol version, and configuration
  hash;
- Subagents source commit, catalog version, schema version, and compiled catalog
  digest;
- the packet schema version, canonical content hash, creation time, and task/stage
  correlation.

Harness persists the packet before asking Herdr to start a worker. Restart and
native resume reuse the persisted packet. A running stage never recompiles
against a newer package, flow, role, skill, capability, or project manifest.

`StagePacketCompiler` is the only module allowed to combine these inputs. Its
interface accepts validated snapshots and returns either one complete packet or a
typed rejection. It does not execute a runtime or perform an external effect.

## 4. PromptX runtime integration

PromptX runs as `agentops` in the control-plane image and is called through a
fixed, version-negotiated JSON adapter. Harness does not install PromptX hooks
into workers or expose a generic PromptX command endpoint.

Harness:

- stores the original request before enrichment;
- supplies only sanitized, bounded, digest-recorded project facts;
- disables PromptX repository traversal and autonomous project-file collection;
- invokes the exact executable built from the pinned submodule;
- uses deterministic gating and rendering as the required baseline;
- permits optional model refinement only through the loopback model broker with a
  task-scoped, revocable capability;
- allowlists the broker endpoint and strips unrelated environment variables;
- validates and bounds every PromptX output before packet compilation;
- records version, gate verdict, reason, task class, quality score, input/output
  digests, fact digests, provider/degraded state, duration, and token usage.

A PromptX timeout or provider failure may use a valid deterministic result and
must append a degraded audit event. Protocol violations, unredacted content,
oversized output, provenance mismatch, or missing required deterministic output
fail closed before dispatch.

PromptX never chooses a Harness flow, role, model alias, skill, tool, capability,
approval, or next stage.

## 5. Subagents catalog integration

The release build compiles the pinned Subagents catalog into Harness role
configuration. The compiler validates:

- supported package and catalog schema versions;
- unique role and department identifiers;
- complete role metadata and resolved handoff references;
- deterministic generation;
- exact skill identifiers, versions, source digests, and license/provenance
  metadata;
- explicit Harness mappings for model aliases and capability profiles;
- absence of executable commands or authority-bearing tool declarations.

Subagents tool profiles and handoffs are advisory source metadata. They never
grant authority. A reviewed Harness mapping converts selected roles into exact
model aliases, skill references, tool definitions, and capability profiles.
Unknown roles, skills, handoffs, tool strings, or mappings fail compilation.

The compiled catalog is immutable release data. Runtime images contain the
compiled roles and required skill artifacts, not the Subagents repository,
installer, update scripts, or global catalog. Worker stage bundles still contain
only the exact role skills declared by the flow snapshot.

## 6. Handoffs and collaboration

Subagents role semantics may inform registered Harness stages and subflows.
Actual orchestration remains declarative and stateful:

- a role handoff may lint or recommend a legal next stage;
- only a snapshotted Harness flow may authorize a transition;
- every transition remains transactional, idempotent, and audit-recorded;
- parallel fan-out is restricted to independent read-only stages;
- one writing worker per worktree remains mandatory;
- each stage returns a typed `StageOutcome` and `HandoffPacket`;
- validation, policy, evidence, and resource admission run before dispatch.

Dynamic role selection may select only from caller-allowed compiled roles and
cannot synthesize a role, skill, tool, or capability at runtime.

## 7. Dependency and upgrade behavior

Builds use recursive, pinned submodules and reject:

- absent or dirty submodules;
- a submodule commit different from the dependency lock;
- unrecognized package or protocol versions;
- nondeterministic compiled output;
- missing checksums, licenses, or source provenance;
- mutable dependency tags or unpinned skill sources.

Harness startup verifies the installed PromptX runtime version, protocol version,
executable digest, and expected configuration. A mismatch prevents worker
dispatch and reports a typed readiness failure.

Subagents is not required on the deployed host because its compiled output is a
release artifact. The release manifest still records its source commit, package
version, catalog digest, and all resolved skill provenance.

Upgrades produce a new immutable Harness image digest and compatibility record.
Rollback restores the prior image, compiled catalog, PromptX artifact, dependency
lock, and configuration together.

## 8. Verification

Required verification includes:

- PromptX adapter contract, version negotiation, deterministic fallback, bounded
  output, redaction, audit, timeout, and broker-only provider tests;
- Subagents schema, deterministic compilation, role uniqueness, handoff
  resolution, capability mapping, skill provenance, and malicious-catalog tests;
- stage-packet canonicalization, immutability, exact-version capture, budget,
  unauthorized-field, digest-mismatch, restart, and native-resume tests;
- prompt-injection, secret-bearing Git metadata, symlink/path escape, environment
  leakage, endpoint allowlist, and global-catalog absence tests;
- missing, dirty, incompatible, and advanced submodule fixtures;
- clean-build, source/artifact provenance, SBOM, immutable-image, update, and
  rollback tests;
- offline PromptX characteristic evaluation and flow simulation for every
  imported role.

An upstream companion test suite is necessary but not sufficient. Harness owns
the integration contract and must independently verify it.

## 9. Acceptance criteria

- The two submodules exist at the approved `packages/` paths with HTTPS fetch
  URLs and pinned commits.
- A clean recursive clone can reproduce both required artifacts.
- PromptX is present in the control-plane image but absent from worker images.
- Subagents source and installers are absent from all runtime images.
- Every dispatched stage references a persisted, canonical
  `StageExecutionPacket`.
- Workers receive only their exact compiled role, skills, tools, and
  capabilities.
- Missing or incompatible companion inputs fail build or readiness checks without
  broadening authority.
- Package changes can be developed upstream, verified independently, and adopted
  by one reviewable Harness pointer update.
