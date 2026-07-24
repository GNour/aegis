# 0003 — OpenViking long-term agent context
Status: accepted for the internal pilot; commercial reuse requires AGPL review
Date: 2026-07-23
Sponsor: Aegis — needs source-linked long-term memory and hierarchical context
that can be rebuilt and audited against Git-backed Markdown.

## 1. Problem & goal

QMD can search canonical Markdown, but it does not model cross-session user and
agent memories or hierarchical L0/L1/L2 context. Aegis needs reviewed memories
and patterns to carry across sessions without letting workers write canonical
knowledge directly.

## 2. Options considered

| Option | Summary | Cost | Maturity | License |
|---|---|---|---|---|
| **OpenViking** | Hierarchical context database with resources, memories, skills, sessions, traceable retrieval, and native Hermes integration | Python/Rust service plus local embedding/extraction models | Active and fast-moving | Main project AGPL-3.0; selected clients/examples Apache-2.0 |
| Git + QMD only | Canonical Markdown and local hybrid search | Lowest runtime and complexity | Mature primitives | Git/QMD licenses |
| General vector database | Embeddings and similarity search without agent-memory semantics | Separate database and custom memory pipeline | Mature | Varies |

## 3. Fit analysis (hard gates — Aegis architecture)

- **RAM (§6):** the server process is not the main cost; Ollama embeddings,
  reranking, and memory extraction models are. The live 23 GiB host can pilot
  them, but indexing is serialized against heavy builds and two-worker
  concurrency. Model memory and latency must be benchmarked before expansion.
- **Exposure (§5):** bind to `127.0.0.1:1933`; no Traefik route or public port.
- **Secrets owner (§4):** `agentops` owns the root/admin key and configuration.
  `hermesops` receives a user-scoped key only if Hermes connects directly.
- **License:** the main project is AGPL-3.0. Internal personal use is accepted.
  Productized/client deployment needs an explicit compliance or commercial
  decision before it becomes a default dependency.
- **Backup impact:** back up configuration, account/key metadata, and
  non-rebuildable memory/session state. Resource indexes derived solely from Git
  are rebuildable and must pass a rebuild drill.

## 4. Upstream-verified install sketch

Verified 2026-07-23 against the official
[deployment guide](https://docs.openviking.ai/en/guides/03-deployment),
[authentication guide](https://docs.openviking.ai/en/guides/04-authentication),
[Hermes integration](https://docs.openviking.ai/en/agent-integrations/05-hermes),
and [FAQ](https://docs.openviking.ai/en/faq/faq).

Install a pinned release in its own environment or rootless container under
`agentops`; do not combine it with Hermes's Python environment. Configure local
storage, Ollama-backed dense embeddings, API-key authentication, and loopback
binding. Disable VikingBot. Run `openviking-server doctor`, then gate readiness on
`/ready`, not only `/health`. Create a dedicated user key for Hermes rather than
sharing the root key.

## 5. Recommendation

Adopt OpenViking as a derived memory/context layer, never as the canonical
ledger. Only Aegis's knowledge stage may submit approved Markdown and sanitized
session summaries. Every indexed record carries project ID, source URI, and Git
commit. Workers have read-only, role-scoped retrieval. Rebuild the resource index
from Git during acceptance and before trusting it in recovery.

## 5a. Adapter implementation note (pilot build)

OpenViking is not running in the development environment. Per the roadmap's port/fake
convention, `aegis.knowledge.openviking.OpenVikingAdapter` is a typed port over a
`Transport`. `recall` returns only memories whose metadata carries the requesting
`project_id` plus a `source_commit` and `source_uri`, so every recalled fact traces
to canonical Git. `HttpTransport` is an authenticated loopback client with bounded
timeouts, a readiness check, and API-key redaction on every error; it is validated
via `httpx.MockTransport`, and `MemoryTransport` backs the filter/ingest tests. When
the service is available, re-verify the search/resource response shapes before
changing production behavior.

## 6. Decision & graduation

- ADR: [0004](../adrs/0004-git-qmd-openviking-knowledge.md).
- Graduates to: the future Aegis numbered build guide.
- Validation: API-key isolation, loopback-only listener, Hermes user-key access,
  source citations, rejected direct canonical writes, readiness checks, backup,
  and a full resource-index rebuild from Git.
