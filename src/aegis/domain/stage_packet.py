"""Immutable ``StageExecutionPacket`` contracts.

A stage packet is the complete, canonical, hash-stable record of everything a worker is
authorized to do for one stage attempt. It captures exact companion identities and a
bounded PromptX enrichment snapshot, and it can never carry a broker token, provider
key, raw credential, advisory upstream tool field, or repository path.
"""

from __future__ import annotations

from pydantic import Field

from aegis.domain.models import (
    CatalogIdentifier,
    DomainRecord,
    FrozenJsonMapping,
    NonNegativeInt,
    PositiveInt,
)
from aegis.domain.ids import UUID7, UtcDatetime

_SHA256 = r"^[0-9a-f]{64}$"


class PromptXIdentity(DomainRecord):
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    package_version: str
    protocol_version: str
    executable_sha256: str = Field(pattern=_SHA256)
    configuration_sha256: str = Field(pattern=_SHA256)


class SubagentsIdentity(DomainRecord):
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    package_version: str
    catalog_schema_version: str
    catalog_sha256: str = Field(pattern=_SHA256)
    provenance_sha256: str = Field(pattern=_SHA256)


class PromptXEnrichmentSnapshot(DomainRecord):
    """Bounded record of the PromptX result. Authority-bearing keys cannot appear here."""

    outcome_code: CatalogIdentifier
    additional_context: str = Field(min_length=1, max_length=32_000)
    task_class: CatalogIdentifier
    quality: str = Field(max_length=64)
    provider_state: CatalogIdentifier
    fact_digests: tuple[str, ...] = Field(max_length=64)
    degraded: bool
    duration_ms: NonNegativeInt
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt


class StagePacketBody(DomainRecord):
    schema_version: PositiveInt
    task_id: UUID7
    flow_run_id: UUID7
    stage_run_id: UUID7
    attempt_ordinal: NonNegativeInt
    task_snapshot: FrozenJsonMapping
    flow_snapshot: FrozenJsonMapping
    stage_snapshot: FrozenJsonMapping
    role_snapshot: FrozenJsonMapping
    model_snapshot: FrozenJsonMapping
    skill_snapshots: tuple[FrozenJsonMapping, ...]
    capability_snapshot: FrozenJsonMapping
    project_snapshot: FrozenJsonMapping
    request_digest: str = Field(pattern=_SHA256)
    promptx_enrichment: PromptXEnrichmentSnapshot
    context_snapshot: FrozenJsonMapping
    tool_definitions: tuple[FrozenJsonMapping, ...]
    broker_capability_reference: str | None = Field(default=None, max_length=256)
    budgets: FrozenJsonMapping
    completion_requirements: FrozenJsonMapping
    artifact_requirements: tuple[FrozenJsonMapping, ...]
    decision_requirements: tuple[FrozenJsonMapping, ...]
    approval_requirements: tuple[FrozenJsonMapping, ...]
    handoff_requirements: FrozenJsonMapping
    promptx: PromptXIdentity
    subagents: SubagentsIdentity


class StagePacketInput(StagePacketBody):
    id: UUID7
    created_at: UtcDatetime

    def packet_values(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class StageExecutionPacket(StagePacketInput):
    canonical_hash: str = Field(pattern=_SHA256)
