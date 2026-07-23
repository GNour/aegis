"""Frozen, data-only records for the Harness control-plane domain."""

import re
from math import isfinite
from types import MappingProxyType
from typing import Annotated, Any, Mapping

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from harness.domain.ids import UtcDatetime, UUID7
from harness.domain.state import TaskState

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | tuple[JsonValue, ...] | Mapping[str, JsonValue]


def _freeze_json(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("JSON floats must be finite")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError("value must be JSON-compatible")


def _freeze_mapping(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return _freeze_json(value)  # type: ignore[return-value]


def _serialize_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _serialize_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize_json(item) for item in value]
    return value


def _ensure_catalog_identifier(value: str) -> str:
    if not value or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value) is None:
        raise ValueError("catalog identifier must be a nonempty safe string")
    return value


FrozenJsonMapping = Annotated[
    Mapping[str, JsonValue],
    BeforeValidator(_freeze_mapping),
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_json, return_type=Any),
]
CatalogIdentifier = Annotated[str, AfterValidator(_ensure_catalog_identifier)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class DomainRecord(BaseModel):
    """Common strict immutable model behavior for persisted records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class TaskManifest(DomainRecord):
    id: UUID7
    project_id: UUID7
    request: str
    acceptance_criteria: tuple[str, ...]
    risk: str
    state: TaskState
    flow_snapshot: FrozenJsonMapping
    source_interface: CatalogIdentifier
    creator_id: UUID7
    budgets: FrozenJsonMapping
    base_commit: str
    branch: str
    worktree: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class FlowRun(DomainRecord):
    id: UUID7
    task_id: UUID7
    flow_id: CatalogIdentifier
    flow_version: PositiveInt
    flow_hash: str
    routing_reason: str
    state: TaskState
    current_stage_id: CatalogIdentifier


class StageRun(DomainRecord):
    id: UUID7
    flow_run_id: UUID7
    stage_id: CatalogIdentifier
    stage_snapshot: FrozenJsonMapping
    role_id: CatalogIdentifier
    model_alias: CatalogIdentifier
    skills: tuple[CatalogIdentifier, ...]
    capability_profile: CatalogIdentifier
    state: TaskState
    ordinal: NonNegativeInt
    budgets: FrozenJsonMapping


class Attempt(DomainRecord):
    id: UUID7
    stage_run_id: UUID7
    runtime: str
    started_at: UtcDatetime
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    tool_tokens: NonNegativeInt
    cost_usd: NonNegativeFloat
    native_session_id: str | None = None
    herdr_session_id: str | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    exit_result: str | None = None


class DecisionRequest(DomainRecord):
    id: UUID7
    task_id: UUID7
    question: str
    options: tuple[str, ...]
    evidence: tuple[str, ...]
    impact: str
    requested_by: UUID7
    resolution: str | None = None


class ApprovalRequest(DomainRecord):
    id: UUID7
    task_id: UUID7
    action_payload_hash: str
    scope: str
    risk: str
    reason: str
    expires_at: UtcDatetime
    nonce: str
    signer_id: UUID7 | None = None
    used_at: UtcDatetime | None = None
    use_event_id: UUID7 | None = None


class SessionLink(DomainRecord):
    id: UUID7
    task_id: UUID7
    stage_run_id: UUID7
    attempt_id: UUID7
    runtime: str
    native_session_id: str | None = None
    herdr_session_id: str | None = None
    sanitized_export_artifact_id: UUID7 | None = None


class HandoffPacket(DomainRecord):
    id: UUID7
    task_id: UUID7
    outcome: str
    changed_files: tuple[str, ...]
    tests: tuple[str, ...]
    decisions: tuple[str, ...]
    risks: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    next_action: str
    commit_id: str | None = None
    commit_ids: tuple[str, ...] = ()


class ArtifactRecord(DomainRecord):
    id: UUID7
    task_id: UUID7
    kind: str
    uri: str
    digest: str
    byte_size: NonNegativeInt
    redaction_class: str
    retention: str
    producer: UUID7


class KnowledgeSync(DomainRecord):
    id: UUID7
    task_id: UUID7
    canonical_commit: str
    state: str
    ready_for_cleanup: bool
    qmd_receipt: str | None = None
    qmd_collection: str | None = None
    qmd_source_commit: str | None = None
    openviking_receipt: str | None = None
    openviking_uri: str | None = None
    openviking_source_commit: str | None = None


class CleanupRecord(DomainRecord):
    id: UUID7
    task_id: UUID7
    target_labels: FrozenJsonMapping
    preconditions: tuple[str, ...]
    actions: tuple[str, ...]
    verified: bool
    state: str
    failure_reason: str | None = None


class AuditEvent(DomainRecord):
    id: UUID7
    sequence: PositiveInt
    event_type: str
    event_version: PositiveInt
    actor_id: UUID7
    correlation_id: UUID7
    payload: FrozenJsonMapping
    prior_hash: str
    event_hash: str
    occurred_at: UtcDatetime
    task_id: UUID7 | None = None
    causation_id: UUID7 | None = None
