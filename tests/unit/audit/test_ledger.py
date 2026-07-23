import json
import hmac
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest

from harness.audit.ledger import Ledger, flush_outbox
from harness.domain.ids import new_uuid7
from harness.storage.sqlite import SQLiteStore


def _signer(payload: bytes) -> str:
    return hmac.new(b"test-only-segment-key", payload, sha256).hexdigest()


def _verifier(payload: bytes, signature: str) -> bool:
    return hmac.compare_digest(_signer(payload), signature)


def _append_from_process(path_text: str, value: int) -> int:
    return int(Ledger(Path(path_text)).append("concurrent", {"value": value})["sequence"])


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


def test_restart_reconciles_a_missing_manifest_after_an_append(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path)
    ledger.append("one", {"value": 1})
    path.with_name(path.name + ".manifest").unlink()

    assert Ledger(path).verify() == []


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


def test_rotation_seals_a_signed_segment_and_links_its_successor(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path, signer=_signer, verifier=_verifier)
    first = ledger.append("one", {"value": 1})
    second = ledger.append("two", {"value": 2})
    sealed_text = path.read_text(encoding="utf-8")

    segment = ledger.rotate()
    third = ledger.append("three", {"value": 3})

    assert segment.read_text(encoding="utf-8") == sealed_text
    manifest = json.loads(segment.with_name(segment.name + ".manifest").read_text(encoding="utf-8"))
    assert manifest["first_sequence"] == first["sequence"]
    assert manifest["terminal_sequence"] == second["sequence"]
    assert third["sequence"] == 3
    assert third["prior_hash"] == second["event_hash"]
    assert Ledger(path, signer=_signer, verifier=_verifier).verify() == []


def test_rotation_requires_a_runtime_signer(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    ledger.append("one", {"value": 1})

    with pytest.raises(ValueError, match="requires a segment manifest signer"):
        ledger.rotate()


def test_restart_recovers_a_missing_active_manifest_after_rotation(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path, signer=_signer, verifier=_verifier)
    ledger.append("one", {"value": 1})
    ledger.rotate()
    ledger.append("two", {"value": 2})
    path.with_name(path.name + ".manifest").unlink()

    restarted = Ledger(path, signer=_signer, verifier=_verifier)
    assert restarted.verify() == []
    assert restarted.append("three", {"value": 3})["sequence"] == 3


def test_tampered_signed_segment_is_rejected_on_restart(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path, signer=_signer, verifier=_verifier)
    ledger.append("one", {"value": 1})
    segment = ledger.rotate()
    manifest_path = segment.with_name(segment.name + ".manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["terminal_hash"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="audit"):
        Ledger(path, signer=_signer, verifier=_verifier)


def test_verify_returns_the_first_position_for_a_malformed_event(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    ledger = Ledger(path)
    ledger.append("one", {"value": 1})
    event = json.loads(path.read_text(encoding="utf-8"))
    del event["event_type"]
    path.write_text(json.dumps(event, separators=(",", ":")) + "\n", encoding="utf-8")

    assert ledger.verify() == [1]


def test_multiple_processes_append_one_contiguous_chain(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as executor:
        sequences = list(executor.map(_append_from_process, [str(path), str(path)], [1, 2]))

    assert sorted(sequences) == [1, 2]
    assert Ledger(path).verify() == []
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


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


def test_restart_replays_a_durable_outbox_event_after_manifest_loss(tmp_path) -> None:
    class MarkFailingStore(SQLiteStore):
        def mark_outbox_flushed(self, sequence: int, claim_token: str, event: dict[str, object]) -> bool:
            raise RuntimeError("simulated database failure")

    database_path = tmp_path / "state.db"
    ledger_path = tmp_path / "audit.jsonl"
    with MarkFailingStore(database_path) as store:
        _create_task(store)
        with pytest.raises(RuntimeError, match="simulated database failure"):
            flush_outbox(store, Ledger(ledger_path), claimer_id=new_uuid7())

    ledger_path.with_name(ledger_path.name + ".manifest").unlink()
    with SQLiteStore(database_path) as restarted:
        assert flush_outbox(restarted, Ledger(ledger_path), claimer_id=new_uuid7()) == 1
        assert restarted.count_unflushed_outbox_events() == 0

    assert Ledger(ledger_path).verify() == []
