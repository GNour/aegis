# Harness documentation

This directory is authoritative for the product and implementation. The
[original request and resolution notes](source/README.md) are preserved under
`source/`; they are historical input, not the current contract.

## Read order

1. [Architecture](architecture.md) — approved system shape and rollout.
2. [Product requirements](specs/00-product-requirements.md) — traceable behavior
   and quality requirements.
3. Subsystem specifications:
   - [Domain and control API](specs/01-domain-and-control-api.md)
   - [Flows, routing, and policy](specs/02-flows-routing-policy.md)
   - [Execution and isolation](specs/03-execution-and-isolation.md)
   - [Context and knowledge](specs/04-context-and-knowledge.md)
   - [Recovery, audit, and cleanup](specs/05-recovery-audit-cleanup.md)
   - [TUI and Hermes interfaces](specs/06-interfaces.md)
   - [Deployment and operations](specs/07-deployment-and-operations.md)
   - [Verification matrix](specs/08-verification-matrix.md)
   - [Requirement traceability](specs/09-traceability.md)
4. [Implementation roadmap](plans/00-implementation-roadmap.md) and its five
   executable subsystem plans.
5. [ADRs](adrs/README.md) for accepted choices and [RFCs](rfcs/README.md) for
   evaluated dependencies.
6. [VPS integration contract](integration/vps-refined.md).

## Status vocabulary

- **proposed** — still under discussion;
- **accepted** — approved for implementation;
- **implemented** — code exists and its acceptance tests pass;
- **superseded** — retained only for history.

No document may claim **implemented** until the referenced verification command
has passed on the current commit.
