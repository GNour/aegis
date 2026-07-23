from datetime import UTC, datetime, timedelta, timezone
from uuid import RFC_4122, UUID

import pytest
from pydantic import ValidationError

from harness.domain.ids import ensure_uuid7, new_uuid7
from harness.domain.models import (
    ApprovalRequest,
    ArtifactRecord,
    Attempt,
    AuditEvent,
    CleanupRecord,
    DecisionRequest,
    FlowRun,
    HandoffPacket,
    KnowledgeSync,
    SessionLink,
    StageRun,
    TaskManifest,
)
from harness.domain.state import TaskState


def identifiers(count: int) -> tuple[str, ...]:
    return tuple(new_uuid7() for _ in range(count))


def task_manifest() -> TaskManifest:
    now = datetime(2020, 1, 1, tzinfo=UTC)
    task_id, project_id, creator_id = identifiers(3)
    return TaskManifest(
        id=task_id,
        project_id=project_id,
        request="Add a task state machine.",
        acceptance_criteria=("Transitions are allowlisted.",),
        risk="low",
        state=TaskState.INTAKE,
        flow_snapshot={"id": "software-change", "steps": ["clarify"]},
        source_interface="operator_tui",
        creator_id=creator_id,
        budgets={"max_cost_usd": 5},
        base_commit="a" * 40,
        branch="harness/task-state",
        worktree="C:/worktrees/task-state",
        created_at=now,
        updated_at=now,
    )


def test_task_manifest_preserves_required_contract_fields() -> None:
    manifest = task_manifest()

    assert manifest.request == "Add a task state machine."
    assert manifest.project_id
    assert manifest.acceptance_criteria == ("Transitions are allowlisted.",)
    assert manifest.state is TaskState.INTAKE
    assert manifest.flow_snapshot == {"id": "software-change", "steps": ("clarify",)}
    assert manifest.source_interface == "operator_tui"
    assert manifest.creator_id
    assert manifest.budgets == {"max_cost_usd": 5}
    assert manifest.base_commit == "a" * 40
    assert manifest.branch == "harness/task-state"
    assert manifest.worktree == "C:/worktrees/task-state"
    assert manifest.created_at.tzinfo is timezone.utc
    assert manifest.updated_at.tzinfo is timezone.utc


def test_task_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TaskManifest(**task_manifest().model_dump(), unexpected="value")


def test_task_manifest_is_frozen() -> None:
    manifest = task_manifest()

    with pytest.raises(ValidationError, match="frozen_instance"):
        manifest.request = "Change it"


def test_cleanup_record_defaults_failure_reason_to_none() -> None:
    record = CleanupRecord(
        id=new_uuid7(),
        task_id=new_uuid7(),
        target_labels={"harness.task_id": "task-123"},
        preconditions=("writes_frozen",),
        actions=("remove_worktree",),
        verified=False,
        state="cleanup_failed",
    )

    assert record.failure_reason is None


def test_frozen_mappings_serialize_roundtrip_and_reject_nested_mutation() -> None:
    manifest = task_manifest()
    cleanup = CleanupRecord(
        id=new_uuid7(),
        task_id=new_uuid7(),
        target_labels={"labels": {"task": "task-123"}},
        preconditions=(),
        actions=(),
        verified=True,
        state="complete",
    )

    with pytest.raises(TypeError):
        manifest.flow_snapshot["id"] = "other"  # type: ignore[index]
    with pytest.raises(TypeError):
        manifest.flow_snapshot["steps"] += ("plan",)  # type: ignore[index,operator]
    with pytest.raises(AttributeError):
        manifest.flow_snapshot["steps"].append("plan")  # type: ignore[index,union-attr]
    with pytest.raises(TypeError):
        cleanup.target_labels["labels"]["task"] = "other"  # type: ignore[index]

    assert isinstance(manifest.model_dump()["flow_snapshot"], dict)
    assert isinstance(cleanup.model_dump()["target_labels"], dict)
    assert TaskManifest.model_validate_json(manifest.model_dump_json()) == manifest
    assert CleanupRecord.model_validate_json(cleanup.model_dump_json()) == cleanup


def test_catalog_references_are_textual_identifiers() -> None:
    flow_id, task_id, stage_run_id = identifiers(3)
    flow = FlowRun(
        id=flow_id,
        task_id=task_id,
        flow_id="feature-delivery",
        flow_version=1,
        flow_hash="a" * 64,
        routing_reason="matched request",
        state=TaskState.CLARIFY,
        current_stage_id="clarify",
    )
    stage = StageRun(
        id=new_uuid7(),
        flow_run_id=stage_run_id,
        stage_id="clarify",
        stage_snapshot={},
        role_id="planner",
        model_alias="codex-frontier",
        skills=("requirements",),
        capability_profile="read-only",
        state=TaskState.CLARIFY,
        ordinal=0,
        budgets={},
    )

    assert flow.flow_id == "feature-delivery"
    assert flow.current_stage_id == "clarify"
    assert stage.role_id == "planner"
    assert stage.capability_profile == "read-only"


def test_flow_run_version_must_be_a_positive_integer() -> None:
    values = dict(
        id=new_uuid7(),
        task_id=new_uuid7(),
        flow_id="feature-delivery",
        flow_version=1,
        flow_hash="a" * 64,
        routing_reason="matched request",
        state=TaskState.CLARIFY,
        current_stage_id="clarify",
    )

    with pytest.raises(ValidationError):
        FlowRun(**{**values, "flow_version": 0})
    with pytest.raises(ValidationError):
        FlowRun(**{**values, "flow_version": "v1"})


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_json_mapping_rejects_non_finite_floats(non_finite: float) -> None:
    values = task_manifest().model_dump()

    with pytest.raises(ValidationError, match="finite"):
        TaskManifest(**{**values, "flow_snapshot": {"bad": non_finite}})
    with pytest.raises(ValidationError, match="finite"):
        TaskManifest(**{**values, "budgets": {"bad": non_finite}})


def test_attempt_numeric_fields_are_strict() -> None:
    values = dict(
        id=new_uuid7(),
        stage_run_id=new_uuid7(),
        runtime="codex",
        started_at=datetime.now(UTC),
        input_tokens=1,
        output_tokens=0,
        tool_tokens=0,
        cost_usd=0.0,
    )

    with pytest.raises(ValidationError):
        Attempt(**{**values, "input_tokens": 1.0})
    with pytest.raises(ValidationError):
        Attempt(**{**values, "cost_usd": "1.25"})


def test_timestamps_are_canonical_utc_and_non_utc_is_rejected() -> None:
    manifest = task_manifest()

    assert '"created_at":"2020-01-01T00:00:00.000000Z"' in manifest.model_dump_json()
    with pytest.raises(ValidationError, match="timestamp must be timezone-aware UTC"):
        TaskManifest(**{**manifest.model_dump(), "created_at": datetime(2020, 1, 1)})
    with pytest.raises(ValidationError, match="timestamp must be timezone-aware UTC"):
        TaskManifest(
            **{**manifest.model_dump(), "created_at": datetime(2020, 1, 1, tzinfo=timezone(timedelta(hours=1)))}
        )


def test_uuid7_generation_and_validation() -> None:
    identifier = new_uuid7()
    parsed = UUID(identifier)

    assert ensure_uuid7(identifier) == identifier
    assert str(parsed) == identifier
    assert parsed.version == 7
    assert parsed.variant == RFC_4122
    with pytest.raises(ValueError, match="canonical UUIDv7"):
        ensure_uuid7("not-a-uuid")
    with pytest.raises(ValueError, match="canonical UUIDv7"):
        ensure_uuid7("00000000-0000-4000-8000-000000000000")


def test_handoff_packet_accepts_original_optional_commit_id() -> None:
    packet = HandoffPacket(
        id=new_uuid7(),
        task_id=new_uuid7(),
        outcome="success",
        changed_files=(),
        tests=(),
        decisions=(),
        risks=(),
        unresolved_questions=(),
        next_action="cleanup",
        commit_id="a" * 40,
    )

    assert packet.commit_id == "a" * 40
    assert packet.commit_ids == ()


def test_all_domain_records_construct_with_minimum_fields_and_serialize() -> None:
    now = datetime.now(UTC)
    ids = identifiers(22)
    records = (
        task_manifest(),
        FlowRun(
            id=ids[0], task_id=ids[1], flow_id="feature-delivery", flow_version=1, flow_hash="hash",
            routing_reason="reason", state=TaskState.INTAKE, current_stage_id="clarify"
        ),
        StageRun(
            id=ids[2], flow_run_id=ids[0], stage_id="clarify", stage_snapshot={}, role_id="planner",
            model_alias="codex-frontier", skills=(), capability_profile="read-only", state=TaskState.CLARIFY,
            ordinal=0, budgets={}
        ),
        Attempt(id=ids[3], stage_run_id=ids[2], runtime="codex", started_at=now, input_tokens=0, output_tokens=0, tool_tokens=0, cost_usd=0.0),
        DecisionRequest(id=ids[4], task_id=ids[1], question="Proceed?", options=(), evidence=(), impact="low", requested_by=ids[5]),
        ApprovalRequest(id=ids[6], task_id=ids[1], action_payload_hash="hash", scope="scope", risk="low", reason="reason", expires_at=now, nonce="nonce"),
        SessionLink(id=ids[7], task_id=ids[1], stage_run_id=ids[2], attempt_id=ids[3], runtime="codex"),
        HandoffPacket(id=ids[8], task_id=ids[1], outcome="success", changed_files=(), tests=(), decisions=(), risks=(), unresolved_questions=(), next_action="cleanup"),
        ArtifactRecord(id=ids[9], task_id=ids[1], kind="log", uri="file:///artifact", digest="hash", byte_size=0, redaction_class="sanitized", retention="180d", producer=ids[10]),
        KnowledgeSync(id=ids[11], task_id=ids[1], canonical_commit="commit", state="complete", ready_for_cleanup=True),
        CleanupRecord(id=ids[12], task_id=ids[1], target_labels={}, preconditions=(), actions=(), verified=True, state="complete"),
        AuditEvent(id=ids[13], sequence=1, event_type="task.created", event_version=1, actor_id=ids[14], correlation_id=ids[15], payload={}, prior_hash="", event_hash="hash", occurred_at=now),
    )

    for record in records:
        assert record.model_dump_json()
