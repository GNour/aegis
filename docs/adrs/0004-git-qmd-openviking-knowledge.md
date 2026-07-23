# 0004 — Use Git Markdown, QMD, and OpenViking as separate knowledge layers
Status: accepted
Date: 2026-07-23

## Context

Aegis needs auditable canonical knowledge, efficient exact document retrieval,
and long-term hierarchical memory. Using one opaque vector store for all three
would make decisions difficult to review or rebuild. Loading all Markdown and all
skills into every session would violate the bounded-context and role-isolation
requirements in [spec 04](../specs/04-context-and-knowledge.md).

## Decision

We will keep approved Markdown and Git history as canonical. QMD will provide
project-isolated, lexical-first Markdown retrieval with optional local semantic
search and reranking. OpenViking will store derived, source-linked long-term
memories and hierarchical context. Aegis is the only writer to canonical
knowledge and records the source Git commit in both retrieval systems. Workers
receive only role-scoped retrieval tools and skill versions.

## Consequences

The corpus is human-readable, reviewable, and rebuildable. Exact docs queries do
not need long memory retrieval, and memory can improve without replacing Git.
Aegis must run two indexes, deduplicate context, enforce collection ACLs,
serialize resource-heavy local models, and verify both indexing receipts before
cleanup. QMD indexes remain disposable; OpenViking's non-rebuildable memory state
joins backups.

## Alternatives rejected

- OpenViking as canonical storage — richer memory, but Git review and deterministic
  rebuilds become secondary.
- QMD only — efficient Markdown search, but no structured cross-session memories
  or hierarchical context.
