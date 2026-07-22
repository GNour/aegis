# Context and knowledge specification

Status: accepted

## 1. Canonical hierarchy

Git-backed Markdown is canonical. The company-brain repository contains policies,
project registry, task summaries, decisions, handoffs, session indexes, artifact
manifests, reminders, and approved reusable knowledge. Product-specific specs and
ADRs remain in their product repository.

Workers cannot push canonical knowledge. They produce structured proposals;
Harness validates and a curator/human approves required classes before commit.

## 2. Skill isolation

Roles declare exact skill IDs and versions. Harness resolves those versions from
the trusted registry, copies only them into a task/stage directory, makes that
directory read-only, and records digests in the stage snapshot. Tool definitions
are generated from the same role/capability profile. No worker receives a global
skill list, unrelated skill description, or unrequested MCP server.

## 3. QMD retrieval

Harness owns QMD collection configuration. Each project has an isolated collection
plus explicit read-only policy/brain collections. Index excludes secret patterns,
raw sessions, archives, dependencies, generated output, and unrelated projects.
Project-controlled update commands are disabled.

`qmd_search` requires collection, query, mode, and limit. `qmd_get` requires an
opaque result URI returned by a prior authorized search. The wrapper rejects
unknown parameters, absolute paths, traversal, unauthorized collections, excessive
limits, and stale task scope. Lexical mode is default; vector/rerank requires a
stage capability and resource admission.

## 4. OpenViking memory

OpenViking binds to loopback with API-key authentication. Harness owns the root
key; direct Hermes access, if retained, uses a separate user key. Each record has
project, type, canonical source URI, Git commit, review state, and ingestion
receipt. Retrieval results without a resolvable source commit are excluded from
worker context.

OpenViking is derived state. Rebuild drills start from Git and approved sanitized
archives. Non-rebuildable memory/session metadata is encrypted in backups.

## 5. Context compiler

The compiler accepts a `ContextRequest` containing task, stage, role, budget, and
query intent. It selects in order: stage contract, acceptance criteria, unresolved
decisions, latest handoff, exact skill text, targeted file/test evidence, lexical
QMD snippets, and source-linked OpenViking memory. It deduplicates by normalized
content digest and stops at per-source and total byte/token ceilings.

The output is a `ContextEnvelope` with ordered sections, source URIs/digests,
estimated tokens, exclusions, and budget reason. Full transcripts are never loaded
by default.

## 6. Preservation transaction

Completion writes Markdown and an artifact manifest, commits them, updates QMD,
syncs that exact commit to OpenViking, waits for both receipts, and records them in
`KnowledgeSync`. If any step fails, the task remains `preserving` or
`recovery_required`; service/worktree deletion is prohibited.
