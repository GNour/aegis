"""Shared fixtures for stage-packet tests."""

import json
from collections.abc import Callable

import pytest

from aegis.domain.ids import new_uuid7
from aegis.domain.stage_packet import StageExecutionPacket, StagePacketInput
from aegis.engine.stage_packets import StagePacketCompiler


def _packet_dict(
    *,
    task_id: str | None = None,
    flow_run_id: str | None = None,
    stage_run_id: str | None = None,
    packet_id: str | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "id": packet_id or new_uuid7(),
        "task_id": task_id or new_uuid7(),
        "flow_run_id": flow_run_id or new_uuid7(),
        "stage_run_id": stage_run_id or new_uuid7(),
        "attempt_ordinal": 0,
        "task_snapshot": {"request": "add caching"},
        "flow_snapshot": {"id": "feature-delivery", "version": 1},
        "stage_snapshot": {"id": "implement"},
        "role_snapshot": {"id": "python-dev"},
        "model_snapshot": {"alias": "implementation"},
        "skill_snapshots": [{"id": "trailofbits/modern-python"}],
        "capability_snapshot": {"profile": "worktree-write"},
        "project_snapshot": {"id": "demo"},
        "request_digest": "a" * 64,
        "promptx_enrichment": {
            "outcome_code": "AEGIS_SUCCESS_DETERMINISTIC",
            "additional_context": "Fact (test_command) — uv run pytest",
            "task_class": "debug",
            "quality": "injected-facts",
            "provider_state": "not-requested",
            "fact_digests": ["b" * 64],
            "degraded": False,
            "duration_ms": 2,
            "input_tokens": 9,
            "output_tokens": 9,
        },
        "context_snapshot": {"budget_tokens": 30000},
        "tool_definitions": [{"name": "qmd_search"}],
        "broker_capability_reference": "broker:task:stage",
        "budgets": {"tokens": 30000},
        "completion_requirements": {"tests": "pass"},
        "artifact_requirements": [{"kind": "diff"}],
        "decision_requirements": [{"kind": "adr"}],
        "approval_requirements": [{"kind": "merge"}],
        "handoff_requirements": {"required": []},
        "promptx": {
            "source_commit": "2" * 40,
            "package_version": "1.0.0-aegis.0",
            "protocol_version": "1",
            "executable_sha256": "3" * 64,
            "configuration_sha256": "4" * 64,
        },
        "subagents": {
            "source_commit": "5" * 40,
            "package_version": "1.0.0-aegis.0",
            "catalog_schema_version": "1",
            "catalog_sha256": "6" * 64,
            "provenance_sha256": "7" * 64,
        },
        "created_at": "2026-07-24T12:00:00.000000Z",
    }


@pytest.fixture
def packet_input_dict() -> dict:
    return _packet_dict()


@pytest.fixture
def packet_input() -> StagePacketInput:
    return StagePacketInput.model_validate_json(json.dumps(_packet_dict()))


PacketFactory = Callable[[str, str, str], StageExecutionPacket]


@pytest.fixture
def stage_packet_factory() -> PacketFactory:
    def make(task_id: str, flow_run_id: str, stage_run_id: str) -> StageExecutionPacket:
        source = StagePacketInput.model_validate_json(
            json.dumps(
                _packet_dict(
                    task_id=task_id, flow_run_id=flow_run_id, stage_run_id=stage_run_id
                )
            )
        )
        return StagePacketCompiler().compile(source)

    return make
