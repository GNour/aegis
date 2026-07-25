---
title: Aegis Documentation
tags:
  - aegis
  - index
  - documentation
---

# Aegis documentation

This directory is authoritative for the product and implementation. The
[[source/README|original request and resolution notes]] are preserved under
`source/`; they are historical input, not the current contract.

## Read order

1. [[architecture|Architecture]] — approved system shape and rollout.
2. [[specs/00-product-requirements|Product requirements]] — traceable behavior
   and quality requirements.
3. Subsystem specifications:
   - [[specs/01-domain-and-control-api|Domain and control API]]
   - [[specs/02-flows-routing-policy|Flows, routing, and policy]]
   - [[specs/03-execution-and-isolation|Execution and isolation]]
   - [[specs/04-context-and-knowledge|Context and knowledge]]
   - [[specs/05-recovery-audit-cleanup|Recovery, audit, and cleanup]]
   - [[specs/06-interfaces|TUI and Hermes interfaces]]
   - [[specs/07-deployment-and-operations|Deployment and operations]]
   - [[specs/08-verification-matrix|Verification matrix]]
   - [[specs/09-traceability|Requirement traceability]]
   - [[specs/10-stage-packets-and-companion-packages|Stage packets and companion packages]]
   - [[superpowers/specs/2026-07-23-container-first-deployment-design|Container-first deployment design]]
4. [[plans/00-implementation-roadmap|Implementation roadmap]]. Its first four
   subsystem plans and the
   [[plans/01a-companion-packages-and-stage-packets|companion-package integration plan]]
   are executable; the deployment plan is explicitly superseded pending its
   container-first rewrite.
5. [[adrs/README|ADRs]] for accepted choices and [[rfcs/README|RFCs]] for
   evaluated dependencies.
6. [[integration/vps-refined|VPS integration contract]].
7. [[maintainer-handoff-promptx-subagents|PromptX and Subagents maintainer handoff]].

## Status vocabulary

- **proposed** — still under discussion;
- **accepted** — approved for implementation;
- **implemented** — code exists and its acceptance tests pass;
- **superseded** — retained only for history.

No document may claim **implemented** until the referenced verification command
has passed on the current commit.
