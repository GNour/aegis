"""A single approval token may be consumed exactly once, even across processes."""

import json


def canonical_body(body: dict[str, object]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_create_task_is_idempotent(client, signed_headers) -> None:
    from aegis.domain.ids import new_uuid7

    body = {"project_id": "demo", "request": "add health route", "flow_id": "auto"}
    raw = canonical_body(body)
    actor_id = new_uuid7()  # the same retrying actor; each call still gets a fresh nonce
    first = client.post(
        "/v1/tasks",
        content=raw,
        headers=signed_headers("POST", "/v1/tasks", body, idempotency_key="same-key", actor_id=actor_id),
    )
    second = client.post(
        "/v1/tasks",
        content=raw,
        headers=signed_headers("POST", "/v1/tasks", body, idempotency_key="same-key", actor_id=actor_id),
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]


def test_approval_token_cannot_be_replayed(client, approval, signed_headers) -> None:
    path = f"/v1/approvals/{approval.id}:approve"
    body = {"action_payload": approval.payload, "comment": "looks fine"}
    raw = canonical_body(body)

    first_headers = signed_headers("POST", path, body, idempotency_key="approve-1")
    first = client.post(path, content=raw, headers=first_headers)

    second_headers = signed_headers("POST", path, body, idempotency_key="approve-1")
    second = client.post(path, content=raw, headers=second_headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "approval_replayed"


def test_approval_replay_is_rejected_even_with_a_valid_fresh_signature(client, approval, signed_headers) -> None:
    # A forged replay carrying a brand new, validly-signed assertion still cannot reuse
    # a token whose approval row is already marked used.
    path = f"/v1/approvals/{approval.id}:approve"
    body = {"action_payload": approval.payload, "comment": None}
    raw = canonical_body(body)
    client.post(path, content=raw, headers=signed_headers("POST", path, body, idempotency_key="k1"))
    replay = client.post(path, content=raw, headers=signed_headers("POST", path, body, idempotency_key="k2"))
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "approval_replayed"


def test_expired_approval_is_rejected(client, store, signed_headers) -> None:
    from datetime import UTC, datetime, timedelta

    from aegis.domain.ids import new_uuid7
    from aegis.policy.approvals import digest

    task_result = store.create_task(
        "expired-seed", {"request": "x"}, actor_id=new_uuid7(), correlation_id=new_uuid7(), causation_id=new_uuid7()
    )
    task_id = str(task_result["task_id"])
    payload = {"action": "task.cancel", "task_id": task_id}
    approval_id = store.create_approval_request(
        task_id=task_id,
        action_payload_hash=digest(payload),
        scope="task.cancel",
        risk="high",
        reason="expired on arrival",
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        nonce=new_uuid7(),
    )
    path = f"/v1/approvals/{approval_id}:approve"
    body = {"action_payload": payload, "comment": None}
    raw = canonical_body(body)
    result = client.post(path, content=raw, headers=signed_headers("POST", path, body, idempotency_key="k"))
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "approval_expired"
