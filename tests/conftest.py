"""Shared fixtures for stage-packet tests and the control-plane API tests."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis.api.app import create_app
from aegis.api.auth import PrincipalAssertion, encode
from aegis.config.catalog import CatalogManager
from aegis.domain.ids import new_uuid7
from aegis.domain.stage_packet import StageExecutionPacket, StagePacketInput
from aegis.engine.stage_packets import StagePacketCompiler
from aegis.policy.approvals import digest
from aegis.storage.sqlite import SQLiteStore


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


# ── control-plane API fixtures ───────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
API_SECRET = b"test-secret-do-not-use-in-production"

_OPERATION_TABLE = {
    ("GET", "/v1/flows"): "flows.read",
    ("POST", "/v1/tasks"): "task.create",
    ("POST", "/v1/notes"): "note.create",
    ("POST", "/v1/reminders"): "reminder.create",
}


def operation_for(method: str, path: str) -> str:
    if (method, path) in _OPERATION_TABLE:
        return _OPERATION_TABLE[(method, path)]
    if path.startswith("/v1/tasks/") and path.endswith(":cancel"):
        return "task.cancel"
    if path.startswith("/v1/tasks/") and path.endswith(":resume"):
        return "task.resume"
    if path.startswith("/v1/tasks/"):
        return "task.read"
    if path.startswith("/v1/approvals/") and path.endswith(":approve"):
        return "approval.approve"
    if path.startswith("/v1/approvals/") and path.endswith(":reject"):
        return "approval.reject"
    raise ValueError(f"no operation mapped for {method} {path}")


def canonical_body(body: dict[str, object]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def store(tmp_path):
    with SQLiteStore(tmp_path / "state.db") as store:
        yield store


@pytest.fixture
def catalog_manager():
    return CatalogManager.load(REPO_ROOT / "config")


@pytest.fixture
def app(store, catalog_manager):
    return create_app(store, catalog_manager, API_SECRET)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def signed_headers():
    def _make(
        method: str,
        path: str,
        body: dict[str, object],
        *,
        idempotency_key: str | None = None,
        actor_id: str | None = None,
        principal_type: str = "operator",
        interface: str = "tui",
        operation: str | None = None,
    ) -> dict[str, str]:
        raw = canonical_body(body) if body else b""
        now = datetime.now(UTC)
        assertion = PrincipalAssertion(
            actor_id=actor_id or new_uuid7(),
            principal_type=principal_type,
            interface=interface,
            operation=operation or operation_for(method, path),
            issued_at=now,
            expires_at=now + timedelta(seconds=60),
            nonce=new_uuid7(),
            body_sha256=hashlib.sha256(raw).hexdigest(),
        )
        token, signature = encode(API_SECRET, assertion)
        headers = {"X-Aegis-Principal": token, "X-Aegis-Signature": signature}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    return _make


class Approval:
    def __init__(self, approval_id: str, task_id: str, payload: dict[str, object]) -> None:
        self.id = approval_id
        self.task_id = task_id
        self.payload = payload


@pytest.fixture
def approval(store: SQLiteStore) -> Approval:
    task_result = store.create_task(
        "seed-approval-task",
        {"request": "destructive cleanup"},
        actor_id=new_uuid7(),
        correlation_id=new_uuid7(),
        causation_id=new_uuid7(),
    )
    task_id = str(task_result["task_id"])
    payload = {"action": "task.cancel", "task_id": task_id}
    approval_id = store.create_approval_request(
        task_id=task_id,
        action_payload_hash=digest(payload),
        scope="task.cancel",
        risk="high",
        reason="destructive cleanup requires approval",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        nonce=new_uuid7(),
    )
    return Approval(approval_id, task_id, payload)
