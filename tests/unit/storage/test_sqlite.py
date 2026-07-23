import sqlite3
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier
from uuid import UUID

import pytest

from harness.domain.ids import ensure_uuid7, new_uuid7
from harness.storage import sqlite as sqlite_module
from harness.storage.sqlite import SQLiteStore

_ACTOR_ID = new_uuid7()
_CORRELATION_ID = new_uuid7()
_CAUSATION_ID = new_uuid7()


def create_task(store: SQLiteStore, key: str, payload: dict[str, str]) -> dict[str, str]:
    return store.create_task(
        key, payload, actor_id=_ACTOR_ID, correlation_id=_CORRELATION_ID, causation_id=_CAUSATION_ID
    )


def test_same_idempotency_key_returns_original_result(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    first = create_task(store, "key-1", {"request": "fix bug"})
    second = create_task(store, "key-1", {"request": "fix bug"})
    assert second == first
    assert store.count_tasks() == 1


def test_reused_key_with_different_payload_is_rejected_without_new_records(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    create_task(store, "key-1", {"request": "fix bug"})

    with pytest.raises(ValueError, match="idempotency key reused with different payload"):
        create_task(store, "key-1", {"request": "ship feature"})

    assert store.count_tasks() == 1
    assert store.count_outbox_events() == 1


def test_reused_key_with_different_sensitive_value_is_rejected(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    create_task(store, "key-1", {"request": "fix bug", "password": "first-value"})

    with pytest.raises(ValueError, match="idempotency key reused with different payload"):
        create_task(store, "key-1", {"request": "fix bug", "password": "second-value"})


def test_outbox_stores_only_request_digest_and_length(tmp_path) -> None:
    project_key = "sk-" + "proj-" + "abcdefghijk"
    github_key = "gh" + "p_" + "abcdefghijk"
    request = f"password=hunter2 api_key=abc credential=/tmp/secret Bearer token-value eyJ.header.payload {project_key} {github_key}"
    with SQLiteStore(tmp_path / "state.db") as store:
        result = store.create_task(
            "key-1", {"request": request}, actor_id=new_uuid7(), correlation_id=new_uuid7(), causation_id=new_uuid7()
        )
        payload = store.outbox_events()[0]["payload"]
        serialized_event = repr(store.outbox_events())

    assert payload == {
        "task_id": result["task_id"],
        "state": "intake",
        "request_sha256": sha256(request.encode("utf-8")).hexdigest(),
        "request_length": len(request),
    }
    for sensitive_value in ("hunter2", "api_key=abc", "/tmp/secret", "token-value", "eyJ.header.payload", project_key, github_key):
        assert sensitive_value not in serialized_event


def test_create_task_requires_uuidv7_lineage_and_rejects_mismatched_replay(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    actor_id = new_uuid7()
    correlation_id = new_uuid7()
    causation_id = new_uuid7()

    with pytest.raises(ValueError, match="canonical UUIDv7"):
        store.create_task(
            "missing", {"request": "fix bug"}, actor_id="not-a-uuid", correlation_id=correlation_id, causation_id=causation_id
        )
    with pytest.raises(ValueError, match="canonical UUIDv7"):
        store.create_task(
            "missing", {"request": "fix bug"}, actor_id=actor_id, correlation_id=correlation_id, causation_id="not-a-uuid"
        )
    first = store.create_task(
        "key-1", {"request": "fix bug"}, actor_id=actor_id, correlation_id=correlation_id, causation_id=causation_id
    )
    assert store.create_task(
        "key-1", {"request": "fix bug"}, actor_id=actor_id, correlation_id=correlation_id, causation_id=causation_id
    ) == first
    with pytest.raises(ValueError, match="idempotency key reused with different metadata"):
        store.create_task(
            "key-1", {"request": "fix bug"}, actor_id=new_uuid7(), correlation_id=correlation_id, causation_id=causation_id
        )


def test_store_uses_durable_sqlite_pragmas(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")

    assert store.pragma("journal_mode") == "wal"
    assert store.pragma("foreign_keys") == 1
    assert store.pragma("synchronous") == 2


def test_pragma_rejects_assignments_before_changing_connection_state(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")

    with pytest.raises(ValueError, match="unsupported pragma"):
        store.pragma("foreign_keys=OFF")

    assert store.pragma("foreign_keys") == 1


def test_migration_is_recorded_once_after_reopening(tmp_path) -> None:
    path = tmp_path / "state.db"
    first = SQLiteStore(path)
    second = SQLiteStore(path)

    assert first.applied_migrations() == ("0001_initial",)
    assert second.applied_migrations() == ("0001_initial",)


def test_created_task_has_canonical_uuid7_and_atomic_outbox_event(tmp_path) -> None:
    with SQLiteStore(tmp_path / "state.db") as store:
        actor_id = new_uuid7()
        correlation_id = new_uuid7()
        causation_id = new_uuid7()
        result = store.create_task("key-1", {"request": "fix bug", "secret": "not persisted in event"}, actor_id=actor_id, principal_type="user", correlation_id=correlation_id, causation_id=causation_id)

        assert str(UUID(result["task_id"])) == result["task_id"]
        assert ensure_uuid7(result["task_id"]) == result["task_id"]
        assert result["state"] == "intake"
        assert store.count_tasks() == 1
        assert store.count_outbox_events() == 1
        event = store.outbox_events()[0]
        assert event["type"] == "task.created"
        assert event["event_version"] == 1
        assert event["actor_id"] == actor_id
        assert event["principal_type"] == "user"
        assert event["correlation_id"] == correlation_id
        assert event["causation_id"] == causation_id
        assert event["idempotency_key"] == "key-1"
        assert event["task_id"] == result["task_id"]
        assert ensure_uuid7(str(event["event_id"])) == event["event_id"]
        assert event["payload"] == {
            "task_id": result["task_id"],
            "state": "intake",
            "request_sha256": sha256(b"fix bug").hexdigest(),
            "request_length": len("fix bug"),
        }
        assert str(event["occurred_at"])


def test_redacts_sensitive_request_before_any_sqlite_persistence(tmp_path) -> None:
    path = tmp_path / "state.db"
    project_key = "sk-" + "proj-" + "abcdefghijk"
    with SQLiteStore(path) as store:
        create_task(store, "key-1", {"request": f"credential: {project_key}"})
        assert project_key not in repr(store.outbox_events())


def test_rejects_migration_checksum_drift(tmp_path) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schema_migrations SET checksum = 'tampered'")

    with pytest.raises(ValueError, match="migration drift detected"):
        SQLiteStore(path)


def test_rejects_preexisting_incomplete_tasks_table(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")

    with pytest.raises(ValueError, match="migration schema mismatch: tasks"):
        SQLiteStore(path)


def test_rejects_tasks_table_without_primary_key_or_not_null_constraints(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE tasks (id TEXT, payload_json TEXT, state TEXT, version INTEGER, "
            "schema_version INTEGER, created_at TEXT)"
        )

    with pytest.raises(ValueError, match="migration constraint mismatch: tasks"):
        SQLiteStore(path)


def test_rejects_tasks_table_with_a_text_version(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, state TEXT NOT NULL, "
            "version TEXT NOT NULL, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL)"
        )

    with pytest.raises(ValueError, match="migration type mismatch: tasks"):
        SQLiteStore(path)


def test_reopening_rejects_a_required_table_dropped_after_migration(tmp_path) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE decision_requests")

    with pytest.raises(ValueError, match="migration schema mismatch: missing decision_requests"):
        SQLiteStore(path)


def test_rejects_preexisting_malformed_flow_runs_table(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE flow_runs (id TEXT PRIMARY KEY, task_id TEXT, schema_version INTEGER NOT NULL)"
        )

    with pytest.raises(ValueError, match="migration schema mismatch: flow_runs"):
        SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0


def test_rejects_flow_runs_foreign_key_to_the_wrong_parent_column(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, state TEXT NOT NULL, "
            "version INTEGER NOT NULL, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE flow_runs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(payload_json), "
            "flow_id TEXT NOT NULL, flow_version INTEGER NOT NULL, flow_hash TEXT NOT NULL, "
            "routing_reason TEXT NOT NULL, state TEXT NOT NULL, current_stage_id TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL)"
        )

    with pytest.raises(ValueError, match="migration foreign key mismatch: flow_runs"):
        SQLiteStore(path)


def test_rejects_flow_runs_with_an_unexpected_foreign_key(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, state TEXT NOT NULL, "
            "version INTEGER NOT NULL, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE flow_runs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), "
            "flow_id TEXT NOT NULL REFERENCES tasks(id), flow_version INTEGER NOT NULL, flow_hash TEXT NOT NULL, "
            "routing_reason TEXT NOT NULL, state TEXT NOT NULL, current_stage_id TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL)"
        )

    with pytest.raises(ValueError, match="migration foreign key mismatch: flow_runs"):
        SQLiteStore(path)


def test_replay_rejects_tampered_response_task_id(tmp_path) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path) as store:
        create_task(store, "key-1", {"request": "fix bug"})
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE idempotency_records SET response_json = ? WHERE key = ?",
            (f'{{"task_id":"{new_uuid7()}","state":"intake"}}', "key-1"),
        )

    with SQLiteStore(path) as store:
        with pytest.raises(ValueError, match="idempotency record integrity error"):
            create_task(store, "key-1", {"request": "fix bug"})


def test_replay_rejects_missing_task_even_when_idempotency_record_matches_it(tmp_path) -> None:
    path = tmp_path / "state.db"
    replacement_id = new_uuid7()
    with SQLiteStore(path) as store:
        create_task(store, "key-1", {"request": "fix bug"})
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "UPDATE idempotency_records SET task_id = ?, response_json = ? WHERE key = ?",
            (replacement_id, f'{{"task_id":"{replacement_id}","state":"intake"}}', "key-1"),
        )

    with SQLiteStore(path) as store:
        with pytest.raises(ValueError, match="idempotency record integrity error"):
            create_task(store, "key-1", {"request": "fix bug"})


def test_replay_returns_original_intake_response_after_task_transitions(tmp_path) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path) as store:
        original = create_task(store, "key-1", {"request": "fix bug"})
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE tasks SET state = 'clarify', version = 2 WHERE id = ?", (original["task_id"],))

    with SQLiteStore(path) as store:
        assert create_task(store, "key-1", {"request": "fix bug"}) == original


def test_migrations_upgrade_and_bootstrap_with_a_future_schema_change(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text(
        (sqlite_module._SCHEMA_DIR / "0001_initial.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )
    upgrade = """-- semicolon in this comment ; must not split a statement
ALTER TABLE tasks ADD COLUMN migration_note TEXT NOT NULL DEFAULT 'contains;a:semicolon';
CREATE TABLE upgrade_markers (id TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT 'marker;value');
CREATE TABLE same_line_one (id TEXT PRIMARY KEY); CREATE TABLE same_line_two (id TEXT PRIMARY KEY);
"""
    upgraded_path = tmp_path / "upgraded.db"
    with SQLiteStore(upgraded_path, schema_dir=migrations) as store:
        assert store.applied_migrations() == ("0001_initial",)
    (migrations / "0002_upgrade.sql").write_text(upgrade, encoding="utf-8")
    with SQLiteStore(upgraded_path, schema_dir=migrations) as store:
        assert store.applied_migrations() == ("0001_initial", "0002_upgrade")

    fresh_path = tmp_path / "fresh.db"
    with SQLiteStore(fresh_path, schema_dir=migrations) as store:
        assert store.applied_migrations() == ("0001_initial", "0002_upgrade")

    for path in (upgraded_path, fresh_path):
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT migration_note FROM tasks LIMIT 1").fetchall() == []
            assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'upgrade_markers'").fetchone()
            assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'same_line_one'").fetchone()
            assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'same_line_two'").fetchone()


def test_migration_rejects_transaction_control_without_committing_outer_work(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text(
        (sqlite_module._SCHEMA_DIR / "0001_initial.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (migrations / "0002_bad.sql").write_text(
        "CREATE TABLE should_rollback (id TEXT PRIMARY KEY); /* comment */ CoMmIt; "
        "CREATE TABLE never_reached (id TEXT PRIMARY KEY);",
        encoding="utf-8",
    )
    path = tmp_path / "state.db"

    with pytest.raises(ValueError, match="transaction control"):
        SQLiteStore(path, schema_dir=migrations)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'tasks'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'should_rollback'").fetchone() is None


def test_migration_rejects_standalone_end_without_committing_outer_work(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text(
        (sqlite_module._SCHEMA_DIR / "0001_initial.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (migrations / "0002_bad.sql").write_text(
        "CREATE TABLE end_should_rollback (id TEXT PRIMARY KEY); END TRANSACTION; invalid sql;",
        encoding="utf-8",
    )
    path = tmp_path / "state.db"

    with pytest.raises(ValueError, match="transaction control"):
        SQLiteStore(path, schema_dir=migrations)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'end_should_rollback'").fetchone() is None


def test_rejects_preexisting_malformed_stage_runs_table(tmp_path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE stage_runs (id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)")

    with pytest.raises(ValueError, match="migration schema mismatch: stage_runs"):
        SQLiteStore(path)


def test_concurrent_fresh_initialization_records_migration_once(tmp_path) -> None:
    path = tmp_path / "state.db"
    barrier = Barrier(2)

    def initialize() -> tuple[str, ...]:
        barrier.wait()
        with SQLiteStore(path) as store:
            return store.applied_migrations()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: initialize(), range(2)))

    assert results == [("0001_initial",), ("0001_initial",)]


def test_failure_after_task_insert_rolls_back_every_record(tmp_path) -> None:
    class FailingStore(SQLiteStore):
        def _after_task_insert(self) -> None:
            raise RuntimeError("injected failure")

    with FailingStore(tmp_path / "state.db") as store:
        with pytest.raises(RuntimeError, match="injected failure"):
            create_task(store, "key-1", {"request": "fix bug"})

        assert store.count_tasks() == 0
        assert store.count_idempotency_records() == 0
        assert store.count_outbox_events() == 0


def test_concurrent_identical_keys_create_one_task_and_return_one_response(tmp_path) -> None:
    path = tmp_path / "state.db"
    with SQLiteStore(path):
        pass

    def create() -> dict[str, str]:
        with SQLiteStore(path) as store:
            return create_task(store, "key-1", {"request": "fix bug"})

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))

    assert results[0] == results[1]
    with SQLiteStore(path) as store:
        assert store.count_tasks() == 1
        assert store.count_outbox_events() == 1
