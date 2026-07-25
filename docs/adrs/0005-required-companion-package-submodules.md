---
title: Maintain PromptX and Subagents as Required Companion Packages
tags:
  - aegis
  - adr
  - companion-packages
---

# 0005 — Maintain PromptX and Subagents as required companion packages
Status: accepted
Date: 2026-07-24

## Context

PromptX provides conservative prompt enrichment and evaluation. Subagents
provides a broad role, skill, and handoff catalog. Aegis benefits from both, and
the same maintainers intend to enhance all three repositories. Direct copies
would drift, while treating both companions as ambient runtime tools would weaken
Aegis policy, skill isolation, and reproducibility.

## Decision

Aegis will track PromptX and Subagents as pinned Git submodules under
`packages/` using HTTPS fetch URLs.

PromptX is a required runtime dependency of the Aegis control plane and is
called through a fixed typed adapter. Subagents is a required build-time catalog
dependency whose validated, compiled output is embedded in Aegis releases.
Neither companion receives orchestration or policy authority, and neither
repository or global installer is mounted into workers.

Aegis maintainers actively maintain and enhance both companion repositories.
Companion changes land on their own branches and in their own history before a
separate Aegis commit advances the pinned submodule pointer. Aegis release
metadata records source commits, package/schema/protocol versions, artifact
digests, licenses, and compatibility evidence.

## Consequences

Recursive clone and submodule integrity become build requirements. Release and
CI tooling must reject missing, dirty, advanced, or incompatible submodules.
PromptX and Subagents must expose versioned machine-readable contracts and
reproducible artifacts. Aegis must maintain catalog mappings, adapter contract
tests, provenance records, upgrade checks, and coordinated rollback.

The split preserves least privilege: PromptX can enrich requests at runtime,
while Subagents supplies reviewed role data without exposing its installer,
global catalog, or textual tool scopes to workers.

## Alternatives rejected

- Install both companions in the runtime — Subagents has no durable runtime
  interface and would add unnecessary supply-chain and authority risk.
- Vendor snapshots into Aegis — simple builds, but duplicated ownership and
  upstream drift.
- Depend only on mutable remote releases — loses source-level maintenance,
  reviewable pins, and reproducible companion development.
