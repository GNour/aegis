"""The versioned local control-plane API (spec 01 sections 4-6).

Exposes exactly the nine FR-001 operations over a Unix-socket-served FastAPI app.
Every request is authenticated with a signed principal assertion (``aegis.api.auth``);
every mutation requires an ``Idempotency-Key`` header. Responses use ``{data, meta}`` on
success and ``{error, meta}`` on failure, with the stable error codes from spec 01
section 6.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aegis.api.auth import AuthError, decode_and_verify
from aegis.config.catalog import CatalogManager
from aegis.domain.ids import new_uuid7
from aegis.domain.state import TaskState, resume_target
from aegis.policy import approvals
from aegis.policy.engine import NONDELEGABLE_ACTIONS, PolicyInput, PolicyOutcome, evaluate
from aegis.storage.sqlite import SQLiteStore

SERVER_VERSION = "0.1.0-dev"

_ERROR_STATUS: dict[str, int] = {
    "validation_failed": 422,
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "state_conflict": 409,
    "idempotency_conflict": 409,
    "approval_expired": 409,
    "approval_replayed": 409,
    "policy_denied": 403,
    "resource_exhausted": 429,
    "provider_wait": 503,
    "recovery_required": 409,
}


class ApiError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTaskBody(StrictModel):
    project_id: str
    request: str
    acceptance_criteria: tuple[str, ...] = ()
    flow_id: str = "auto"
    risk: str = "low"


class ApproveBody(StrictModel):
    action_payload: dict[str, object]
    comment: str | None = None


class RejectBody(StrictModel):
    reason: str


class CancelBody(StrictModel):
    reason: str
    cleanup_mode: str = "graceful"


class ResumeBody(StrictModel):
    expected_state: str
    expected_version: int
    reason: str


class NoteBody(StrictModel):
    project_id: str | None = None
    task_id: str | None = None
    markdown_text: str
    source_metadata: dict[str, object] = Field(default_factory=dict)


class ReminderBody(StrictModel):
    message: str
    schedule: str
    timezone: str


def _meta(request: Request) -> dict[str, object]:
    return {
        "request_id": new_uuid7(),
        "correlation_id": request.headers.get("X-Correlation-Id", new_uuid7()),
        "server_version": SERVER_VERSION,
    }


def _ok(data: object, request: Request, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"data": data, "meta": _meta(request)}, status_code=status_code)


def _err(code: str, message: str, request: Request) -> JSONResponse:
    status_code = _ERROR_STATUS.get(code, 400)
    return JSONResponse(
        {"error": {"code": code, "message": message}, "meta": _meta(request)},
        status_code=status_code,
    )


def _deterministic_uuid7(seed: str) -> str:
    """A UUIDv7-shaped value derived deterministically from ``seed``.

    Used to derive correlation/causation IDs from an Idempotency-Key: a genuine retry
    (same key, same body) must present store.create_task with byte-identical metadata
    on every attempt, so those IDs cannot be freshly randomized per HTTP call the way a
    one-shot principal-assertion nonce is.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest[:16], "big")
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0b11 << 62)
    value |= 0b10 << 62
    return str(UUID(int=value))


def _request_hash(body: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def create_app(store: SQLiteStore, catalog_manager: CatalogManager, secret: bytes) -> FastAPI:
    app = FastAPI(title="Aegis control plane")

    async def authenticate(request: Request, operation: str) -> Any:
        token = request.headers.get("X-Aegis-Principal")
        signature = request.headers.get("X-Aegis-Signature")
        if not token or not signature:
            raise AuthError("missing principal assertion")
        body = await request.body()
        return decode_and_verify(
            secret, token, signature,
            operation=operation, body=body, now=datetime.now(UTC),
            claim_nonce=store.claim_nonce,
        )

    def _idempotency_key(request: Request) -> str:
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise ApiError("validation_failed", "Idempotency-Key header is required")
        return key

    async def _json_body(request: Request) -> dict[str, object]:
        raw = await request.body()
        try:
            data = json.loads(raw) if raw else {}
        except ValueError as error:
            raise ApiError("validation_failed", "request body must be valid JSON") from error
        if not isinstance(data, dict):
            raise ApiError("validation_failed", "request body must be a JSON object")
        return data

    def _validate(model_cls: type[StrictModel], data: dict[str, object]) -> Any:
        try:
            return model_cls.model_validate(data)
        except Exception as error:  # pydantic.ValidationError
            raise ApiError("validation_failed", str(error)) from error

    @app.exception_handler(AuthError)
    async def _auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
        return _err(exc.code, str(exc), request)

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _err(exc.code, exc.message, request)

    @app.exception_handler(approvals.ApprovalError)
    async def _approval_error_handler(
        request: Request, exc: approvals.ApprovalError
    ) -> JSONResponse:
        return _err(exc.code, str(exc), request)

    @app.get("/v1/flows")
    async def list_flows(request: Request) -> JSONResponse:
        await authenticate(request, "flows.read")
        catalog = catalog_manager.current
        flows = [
            {
                "flow_id": flow_id,
                "version": flow.doc.version,
                "input_schema": flow.doc.input_schema,
                "accepted_intents": list(flow.doc.accepted_intents),
            }
            for flow_id, flow in sorted(catalog.flows.items())
        ]
        return _ok({"flows": flows}, request)

    @app.post("/v1/tasks", status_code=201)
    async def create_task(request: Request) -> JSONResponse:
        principal = await authenticate(request, "task.create")
        key = _idempotency_key(request)
        body = _validate(CreateTaskBody, await _json_body(request))
        result = store.create_task(
            key,
            {
                "project_id": body.project_id,
                "request": body.request,
                "flow_id": body.flow_id,
                "risk": body.risk,
            },
            actor_id=principal.actor_id,
            principal_type=principal.principal_type,
            correlation_id=_deterministic_uuid7(f"correlation:{key}"),
            causation_id=_deterministic_uuid7(f"causation:{key}"),
        )
        return _ok(result, request, status_code=201)

    @app.get("/v1/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> JSONResponse:
        await authenticate(request, "task.read")
        task = store.get_task(task_id)
        if task is None:
            raise ApiError("not_found", f"unknown task: {task_id}")
        return _ok(
            {
                "task_id": task["task_id"],
                "state": task["state"],
                "version": task["version"],
                "waits": [],
                "decisions": [],
                "sessions": [],
                "artifacts": [],
            },
            request,
        )

    @app.post("/v1/approvals/{approval_id}:approve")
    async def approve(approval_id: str, request: Request) -> JSONResponse:
        principal = await authenticate(request, "approval.approve")
        _idempotency_key(request)
        body = _validate(ApproveBody, await _json_body(request))
        record = approvals.consume(
            store, approval_id, body.action_payload,
            actor_id=principal.actor_id, use_event_id=new_uuid7(), now=datetime.now(UTC),
        )
        return _ok({"approval_id": record.id, "task_id": record.task_id, "used": True}, request)

    @app.post("/v1/approvals/{approval_id}:reject")
    async def reject(approval_id: str, request: Request) -> JSONResponse:
        principal = await authenticate(request, "approval.reject")
        _idempotency_key(request)
        _validate(RejectBody, await _json_body(request))
        record = approvals.reject(
            store, approval_id,
            actor_id=principal.actor_id, use_event_id=new_uuid7(), now=datetime.now(UTC),
        )
        return _ok({"approval_id": record.id, "task_id": record.task_id, "used": True}, request)

    @app.post("/v1/tasks/{task_id}:cancel")
    async def cancel_task(task_id: str, request: Request) -> JSONResponse:
        principal = await authenticate(request, "task.cancel")
        key = _idempotency_key(request)
        body = _validate(CancelBody, await _json_body(request))
        task = store.get_task(task_id)
        if task is None:
            raise ApiError("not_found", f"unknown task: {task_id}")

        action = "task.cancel.destructive" if body.cleanup_mode == "destructive" else "task.cancel"
        decision = evaluate(PolicyInput(action=action, risk="high" if action in NONDELEGABLE_ACTIONS else "low"))

        if decision.outcome is PolicyOutcome.DENY_NONDELEGABLE:
            escalation_id = store.create_approval_request(
                task_id=task_id,
                action_payload_hash=approvals.digest({"action": action, "task_id": task_id}),
                scope=action,
                risk="nondelegable",
                reason=decision.reason,
                expires_at=datetime.now(UTC).isoformat(),
                nonce=new_uuid7(),
            )
            raise ApiError(
                "policy_denied", f"{decision.reason} (escalation: {escalation_id})"
            )

        request_hash = _request_hash(
            {"task_id": task_id, "reason": body.reason, "cleanup_mode": body.cleanup_mode}
        )

        def build() -> dict[str, object]:
            return store.update_task_state_in_transaction(
                task_id,
                expected_state=str(task["state"]),
                expected_version=cast(int, task["version"]),
                new_state=TaskState.CANCELLED.value,
                event_type="task.cancelled",
                reason=body.reason,
                actor_id=principal.actor_id,
                principal_type=principal.principal_type,
                correlation_id=new_uuid7(),
                causation_id=new_uuid7(),
                idempotency_key=key,
            )

        try:
            result = store.run_idempotent(key, "task.cancel", request_hash, build)
        except ValueError as error:
            raise ApiError(
                "idempotency_conflict" if "idempotency_conflict" in str(error) else "state_conflict",
                str(error),
            ) from error
        return _ok(result, request)

    @app.post("/v1/tasks/{task_id}:resume")
    async def resume_task(task_id: str, request: Request) -> JSONResponse:
        principal = await authenticate(request, "task.resume")
        key = _idempotency_key(request)
        body = _validate(ResumeBody, await _json_body(request))
        try:
            target = resume_target(TaskState(body.expected_state))
        except ValueError as error:
            raise ApiError("state_conflict", str(error)) from error

        request_hash = _request_hash(
            {
                "task_id": task_id,
                "expected_state": body.expected_state,
                "expected_version": body.expected_version,
                "reason": body.reason,
            }
        )

        def build() -> dict[str, object]:
            return store.update_task_state_in_transaction(
                task_id,
                expected_state=body.expected_state,
                expected_version=body.expected_version,
                new_state=target.value,
                event_type="task.resumed",
                reason=body.reason,
                actor_id=principal.actor_id,
                principal_type=principal.principal_type,
                correlation_id=new_uuid7(),
                causation_id=new_uuid7(),
                idempotency_key=key,
            )

        try:
            result = store.run_idempotent(key, "task.resume", request_hash, build)
        except (ValueError, LookupError) as error:
            code = "not_found" if isinstance(error, LookupError) else "state_conflict"
            if isinstance(error, ValueError) and "idempotency_conflict" in str(error):
                code = "idempotency_conflict"
            raise ApiError(code, str(error)) from error
        return _ok(result, request)

    @app.post("/v1/notes", status_code=201)
    async def create_note(request: Request) -> JSONResponse:
        await authenticate(request, "note.create")
        key = _idempotency_key(request)
        body = _validate(NoteBody, await _json_body(request))
        request_hash = _request_hash(body.model_dump())

        def build() -> dict[str, object]:
            note_id = store.create_note_proposal(
                project_id=body.project_id,
                task_id=body.task_id,
                markdown_text=body.markdown_text,
                source_metadata=body.source_metadata,
            )
            return {"note_id": note_id}

        try:
            result = store.run_idempotent(key, "note.create", request_hash, build)
        except ValueError as error:
            raise ApiError("idempotency_conflict", str(error)) from error
        return _ok(result, request, status_code=201)

    @app.post("/v1/reminders", status_code=201)
    async def create_reminder(request: Request) -> JSONResponse:
        await authenticate(request, "reminder.create")
        key = _idempotency_key(request)
        body = _validate(ReminderBody, await _json_body(request))
        request_hash = _request_hash(body.model_dump())

        def build() -> dict[str, object]:
            reminder_id = store.create_reminder(
                message=body.message, schedule=body.schedule, timezone=body.timezone
            )
            return {"reminder_id": reminder_id}

        try:
            result = store.run_idempotent(key, "reminder.create", request_hash, build)
        except ValueError as error:
            raise ApiError("idempotency_conflict", str(error)) from error
        return _ok(result, request, status_code=201)

    return app
