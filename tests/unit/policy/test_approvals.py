from datetime import UTC, datetime, timedelta

import pytest

from aegis.domain.ids import new_uuid7
from aegis.policy.approvals import (
    ApprovalDigestMismatchError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalReplayedError,
    consume,
    digest,
)
from aegis.storage.sqlite import SQLiteStore


@pytest.fixture
def store(tmp_path):
    with SQLiteStore(tmp_path / "state.db") as store:
        yield store


def _seed_task(store: SQLiteStore) -> str:
    result = store.create_task(
        "seed-key",
        {"request": "add caching"},
        actor_id=new_uuid7(),
        correlation_id=new_uuid7(),
        causation_id=new_uuid7(),
    )
    return str(result["task_id"])


def _make_approval(store: SQLiteStore, action_payload: dict, *, expires_in_seconds: int = 3600) -> str:
    task_id = _seed_task(store)
    return store.create_approval_request(
        task_id=task_id,
        action_payload_hash=digest(action_payload),
        scope="task.cancel",
        risk="high",
        reason="destructive cleanup",
        expires_at=(datetime.now(UTC) + timedelta(seconds=expires_in_seconds)).isoformat(),
        nonce=new_uuid7(),
    )


def test_consume_succeeds_once(store: SQLiteStore) -> None:
    payload = {"action": "task.cancel", "task_id": "x"}
    approval_id = _make_approval(store, payload)
    record = consume(
        store, approval_id, payload, actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC)
    )
    assert record.id == approval_id


def test_consume_twice_raises_replayed(store: SQLiteStore) -> None:
    payload = {"action": "task.cancel", "task_id": "x"}
    approval_id = _make_approval(store, payload)
    consume(store, approval_id, payload, actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC))
    with pytest.raises(ApprovalReplayedError):
        consume(store, approval_id, payload, actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC))


def test_consume_expired_raises(store: SQLiteStore) -> None:
    payload = {"action": "task.cancel", "task_id": "x"}
    approval_id = _make_approval(store, payload, expires_in_seconds=-10)
    with pytest.raises(ApprovalExpiredError):
        consume(store, approval_id, payload, actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC))


def test_consume_mismatched_payload_raises(store: SQLiteStore) -> None:
    approval_id = _make_approval(store, {"action": "task.cancel", "task_id": "x"})
    with pytest.raises(ApprovalDigestMismatchError):
        consume(
            store, approval_id, {"action": "task.cancel", "task_id": "different"},
            actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC),
        )


def test_consume_unknown_approval_raises_not_found(store: SQLiteStore) -> None:
    with pytest.raises(ApprovalNotFoundError):
        consume(
            store, new_uuid7(), {"action": "x"},
            actor_id=new_uuid7(), use_event_id=new_uuid7(), now=datetime.now(UTC),
        )
