"""Integration coverage for the nine FR-001 control-plane operations."""

import json

from aegis.domain.ids import new_uuid7


def canonical_body(body: dict[str, object]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _post(client, signed_headers, path: str, body: dict[str, object], *, idempotency_key: str) -> object:
    return client.post(
        path,
        content=canonical_body(body),
        headers=signed_headers("POST", path, body, idempotency_key=idempotency_key),
    )


def _create_task(client, signed_headers, *, request: str = "add caching") -> str:
    body = {"project_id": "demo", "request": request, "flow_id": "auto"}
    result = _post(client, signed_headers, "/v1/tasks", body, idempotency_key=new_uuid7())
    assert result.status_code == 201, result.text
    return result.json()["data"]["task_id"]


# ── GET /v1/flows ────────────────────────────────────────────────────────────
def test_list_flows_returns_the_compiled_catalog(client, signed_headers) -> None:
    result = client.get("/v1/flows", headers=signed_headers("GET", "/v1/flows", {}))
    assert result.status_code == 200
    flows = result.json()["data"]["flows"]
    assert [f["flow_id"] for f in flows] == ["feature-delivery"]


def test_flows_requires_authentication(client) -> None:
    result = client.get("/v1/flows")
    assert result.status_code == 401
    assert result.json()["error"]["code"] == "unauthorized"


# ── POST /v1/tasks, GET /v1/tasks/{id} ──────────────────────────────────────
def test_create_and_read_task(client, signed_headers) -> None:
    task_id = _create_task(client, signed_headers)
    path = f"/v1/tasks/{task_id}"
    result = client.get(path, headers=signed_headers("GET", path, {}, operation="task.read"))
    assert result.status_code == 200
    assert result.json()["data"]["state"] == "intake"


def test_read_unknown_task_is_not_found(client, signed_headers) -> None:
    path = f"/v1/tasks/{new_uuid7()}"
    result = client.get(path, headers=signed_headers("GET", path, {}, operation="task.read"))
    assert result.status_code == 404
    assert result.json()["error"]["code"] == "not_found"


def test_create_task_requires_idempotency_key(client, signed_headers) -> None:
    body = {"project_id": "demo", "request": "x", "flow_id": "auto"}
    result = client.post(
        "/v1/tasks", content=canonical_body(body), headers=signed_headers("POST", "/v1/tasks", body)
    )
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "validation_failed"


def test_create_task_rejects_unknown_field(client, signed_headers) -> None:
    body = {"project_id": "demo", "request": "x", "flow_id": "auto", "unknown_field": 1}
    result = client.post(
        "/v1/tasks",
        content=canonical_body(body),
        headers=signed_headers("POST", "/v1/tasks", body, idempotency_key=new_uuid7()),
    )
    assert result.status_code == 422


# ── task cancel / resume ─────────────────────────────────────────────────────
def test_cancel_task_autonomous(client, signed_headers) -> None:
    task_id = _create_task(client, signed_headers)
    path = f"/v1/tasks/{task_id}:cancel"
    body = {"reason": "no longer needed", "cleanup_mode": "graceful"}
    result = _post(client, signed_headers, path, body, idempotency_key=new_uuid7())
    assert result.status_code == 200, result.text
    assert result.json()["data"]["state"] == "cancelled"


def test_cancel_task_is_idempotent(client, signed_headers) -> None:
    task_id = _create_task(client, signed_headers)
    path = f"/v1/tasks/{task_id}:cancel"
    body = {"reason": "no longer needed", "cleanup_mode": "graceful"}
    key = new_uuid7()
    first = _post(client, signed_headers, path, body, idempotency_key=key)
    second = _post(client, signed_headers, path, body, idempotency_key=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


def test_destructive_cancel_is_denied_nondelegable(client, signed_headers) -> None:
    task_id = _create_task(client, signed_headers)
    path = f"/v1/tasks/{task_id}:cancel"
    body = {"reason": "wipe it", "cleanup_mode": "destructive"}
    result = _post(client, signed_headers, path, body, idempotency_key=new_uuid7())
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "policy_denied"


def test_cancel_from_terminal_state_is_a_state_conflict(client, signed_headers) -> None:
    task_id = _create_task(client, signed_headers)
    cancel_path = f"/v1/tasks/{task_id}:cancel"
    _post(client, signed_headers, cancel_path, {"reason": "r1"}, idempotency_key=new_uuid7())
    # already cancelled; a differently-keyed second cancel attempt hits the domain
    # allowlist (CANCELLED accepts no further transitions), not the idempotency cache.
    result = _post(client, signed_headers, cancel_path, {"reason": "r2"}, idempotency_key=new_uuid7())
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "state_conflict"


# ── notes / reminders ────────────────────────────────────────────────────────
def test_create_note(client, signed_headers) -> None:
    body = {"project_id": "demo", "task_id": None, "markdown_text": "# heads up", "source_metadata": {"via": "test"}}
    result = _post(client, signed_headers, "/v1/notes", body, idempotency_key=new_uuid7())
    assert result.status_code == 201
    assert "note_id" in result.json()["data"]


def test_create_reminder(client, signed_headers) -> None:
    body = {"message": "check the build", "schedule": "2026-08-01T09:00:00Z", "timezone": "UTC"}
    result = _post(client, signed_headers, "/v1/reminders", body, idempotency_key=new_uuid7())
    assert result.status_code == 201
    assert "reminder_id" in result.json()["data"]


def test_reminder_is_idempotent(client, signed_headers) -> None:
    body = {"message": "check the build", "schedule": "2026-08-01T09:00:00Z", "timezone": "UTC"}
    key = new_uuid7()
    first = _post(client, signed_headers, "/v1/reminders", body, idempotency_key=key)
    second = _post(client, signed_headers, "/v1/reminders", body, idempotency_key=key)
    assert first.json()["data"] == second.json()["data"]


def test_idempotency_key_reused_with_different_body_conflicts(client, signed_headers) -> None:
    key = new_uuid7()
    body1 = {"message": "a", "schedule": "2026-08-01T09:00:00Z", "timezone": "UTC"}
    body2 = {"message": "b", "schedule": "2026-08-01T09:00:00Z", "timezone": "UTC"}
    first = _post(client, signed_headers, "/v1/reminders", body1, idempotency_key=key)
    second = _post(client, signed_headers, "/v1/reminders", body2, idempotency_key=key)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_conflict"


# ── approvals ────────────────────────────────────────────────────────────────
def test_reject_approval(client, signed_headers, approval) -> None:
    path = f"/v1/approvals/{approval.id}:reject"
    body = {"reason": "not needed after all"}
    result = _post(client, signed_headers, path, body, idempotency_key=new_uuid7())
    assert result.status_code == 200
    assert result.json()["data"]["used"] is True


def test_approve_with_wrong_payload_is_digest_mismatch(client, signed_headers, approval) -> None:
    path = f"/v1/approvals/{approval.id}:approve"
    body = {"action_payload": {"action": "task.cancel", "task_id": "not-the-real-task"}, "comment": None}
    result = _post(client, signed_headers, path, body, idempotency_key=new_uuid7())
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "validation_failed"


def test_approve_unknown_id_is_not_found(client, signed_headers) -> None:
    path = f"/v1/approvals/{new_uuid7()}:approve"
    body = {"action_payload": {"action": "x"}, "comment": None}
    result = _post(client, signed_headers, path, body, idempotency_key=new_uuid7())
    assert result.status_code == 404
