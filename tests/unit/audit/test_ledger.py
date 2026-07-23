import json

import pytest

from harness.audit.ledger import Ledger, flush_outbox
from harness.domain.ids import new_uuid7
from harness.storage.sqlite import SQLiteStore


def _create_task(store: SQLiteStore) -> dict[str, str]:
    return store.create_task(
        "idempotency-key",
        {"request": "fix an audit bug"},
        actor_id=new_uuid7(),
        correlation_id=new_uuid7(),
        causation_id=new_uuid7(),
    )


def test_modified_event_breaks_chain(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    ledger.append("one", {"value": 1})
    ledger.append("two", {"value": 2})
    path = tmp_path / "audit.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"value":1', '"value":9'), encoding="utf-8")

    assert ledger.verify() == [1]


def test_missing_terminal_event_breaks_manifest_check(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    ledger.append("one", {"value": 1})
    ledger.append("two", {"value": 2})
    path = tmp_path / "audit.jsonl"
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    assert ledger.verify() == [2]


def test_missing_manifest_after_an_append_is_detected(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path)
    ledger.append("one", {"value": 1})
    path.with_name(path.name + ".manifest").unlink()

    assert ledger.verify() == [2]


def test_flushes_committed_outbox_once_and_survives_restart(tmp_path) -> None:
    database_path = tmp_path / "state.db"
    ledger = Ledger(tmp_path / "audit.jsonl")
    with SQLiteStore(database_path) as store:
        result = _create_task(store)
        assert flush_outbox(store, ledger, claimer_id=new_uuid7()) == 1
        assert flush_outbox(store, ledger, claimer_id=new_uuid7()) == 0
        assert store.count_unflushed_outbox_events() == 0
        assert store.count_audit_events() == 1

    with SQLiteStore(database_path) as restarted:
        assert flush_outbox(restarted, ledger, claimer_id=new_uuid7()) == 0
        assert restarted.count_audit_events() == 1

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["task_id"] == result["task_id"]
    assert event["sequence"] == 1
    assert "request" not in event["payload"]
    assert ledger.verify() == []


def test_outbox_claims_only_one_contiguous_unflushed_prefix(tmp_path) -> None:
    with SQLiteStore(tmp_path / "state.db") as store:
        _create_task(store)
        store.create_task(
            "second-idempotency-key",
            {"request": "second request"},
            actor_id=new_uuid7(),
            correlation_id=new_uuid7(),
            causation_id=new_uuid7(),
        )

        first_claim = store.claim_outbox_events(new_uuid7(), limit=2)
        second_claim = store.claim_outbox_events(new_uuid7(), limit=2)

    assert [event["sequence"] for event in first_claim] == [1, 2]
    assert second_claim == ()
    assert "second request" not in repr(first_claim)


def test_flush_retries_an_already_appended_event_after_mark_failure(tmp_path) -> None:
    class MarkFailingStore(SQLiteStore):
        failed = False

        def mark_outbox_flushed(self, sequence: int, claim_token: str, event: dict[str, object]) -> bool:
            if not self.failed:
                self.failed = True
                raise RuntimeError("simulated database failure")
            return super().mark_outbox_flushed(sequence, claim_token, event)

    database_path = tmp_path / "state.db"
    ledger = Ledger(tmp_path / "audit.jsonl")
    with MarkFailingStore(database_path) as store:
        _create_task(store)
        with pytest.raises(RuntimeError, match="simulated database failure"):
            flush_outbox(store, ledger, claimer_id=new_uuid7())

        assert store.count_unflushed_outbox_events() == 1
        assert flush_outbox(store, ledger, claimer_id=new_uuid7()) == 1

    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert ledger.verify() == []
