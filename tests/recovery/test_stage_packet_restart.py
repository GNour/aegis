"""A persisted stage packet must reload unchanged after a process restart."""

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


def test_restart_reuses_persisted_packet(tmp_path, stage_packet_factory) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path) as first:
        packet = stage_packet_factory(*_seed_parents(first))
        first.save_stage_packet(packet)
    with SQLiteStore(path) as restarted:
        reloaded = restarted.get_stage_packet_for_resume(packet.stage_run_id)
    assert reloaded == packet
    assert reloaded.canonical_hash == packet.canonical_hash
