import pytest

from aegis.domain.ids import new_uuid7
from aegis.storage.sqlite import SQLiteStore


def _seed_parents(store: SQLiteStore) -> tuple[str, str, str]:
    task_id, flow_run_id, stage_run_id = new_uuid7(), new_uuid7(), new_uuid7()
    conn = store._connection
    conn.execute(
        "INSERT INTO tasks (id, payload_json, state, version, schema_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "{}", "intake", 1, 1, "2026-07-24T12:00:00Z"),
    )
    conn.execute(
        "INSERT INTO flow_runs (id, task_id, flow_id, flow_version, flow_hash, routing_reason, "
        "state, current_stage_id, schema_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (flow_run_id, task_id, "feature-delivery", 1, "a" * 64, "auto", "running", "implement", 1),
    )
    conn.execute(
        "INSERT INTO stage_runs (id, flow_run_id, stage_id, stage_snapshot_json, role_id, "
        "model_alias, skills_json, capability_profile, state, ordinal, budgets_json, schema_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (stage_run_id, flow_run_id, "implement", "{}", "python-dev", "implementation", "[]",
         "worktree-write", "pending", 0, "{}", 1),
    )
    return task_id, flow_run_id, stage_run_id


@pytest.fixture
def store(tmp_path):
    with SQLiteStore(tmp_path / "state.db") as store:
        yield store


def test_store_inserts_one_exact_packet(store, stage_packet_factory) -> None:
    packet = stage_packet_factory(*_seed_parents(store))
    store.save_stage_packet(packet)
    assert store.get_stage_packet(packet.stage_run_id) == packet
    store.save_stage_packet(packet)  # idempotent
    assert store.get_stage_packet(packet.stage_run_id) == packet


def test_changed_packet_for_same_stage_is_rejected(store, stage_packet_factory) -> None:
    task_id, flow_run_id, stage_run_id = _seed_parents(store)
    packet = stage_packet_factory(task_id, flow_run_id, stage_run_id)
    store.save_stage_packet(packet)
    changed = packet.model_copy(update={"canonical_hash": "f" * 64})
    with pytest.raises(ValueError, match="stage packet"):
        store.save_stage_packet(changed)


def test_missing_packet_returns_none(store) -> None:
    assert store.get_stage_packet(new_uuid7()) is None


def test_resume_seam_returns_stored_packet(store, stage_packet_factory) -> None:
    packet = stage_packet_factory(*_seed_parents(store))
    store.save_stage_packet(packet)
    assert store.get_stage_packet_for_resume(packet.stage_run_id) == packet


def test_tampered_json_fails_integrity(store, stage_packet_factory) -> None:
    packet = stage_packet_factory(*_seed_parents(store))
    store.save_stage_packet(packet)
    store._connection.execute(
        "UPDATE stage_execution_packets SET packet_json = ? WHERE stage_run_id = ?",
        ('{"tampered": true}', packet.stage_run_id),
    )
    with pytest.raises(ValueError):
        store.get_stage_packet(packet.stage_run_id)
