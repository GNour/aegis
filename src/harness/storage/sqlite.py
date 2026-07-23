"""Transactional SQLite state store."""

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self, cast

from harness.domain.ids import ensure_uuid7, new_uuid7

_SCHEMA_DIR: Final = Path(__file__).with_name("schema")
_SENSITIVE_KEY: Final = re.compile(r"(?:api[_-]?key|authorization|credential|password|secret|token)", re.I)
_BEARER_VALUE: Final = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]+=*", re.I)
_TOKEN_VALUE: Final = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_-]{8,})\b", re.I)
_REDACTED: Final = "[REDACTED]"
_TABLE_SPECS: Final[dict[str, tuple[frozenset[str], dict[str, str]]]] = {
    "tasks": (frozenset({"id", "payload_json", "state", "version", "schema_version", "created_at"}), {}),
    "idempotency_records": (frozenset({"key", "payload_json", "task_id", "response_json", "created_at", "actor_id", "principal_type", "correlation_id", "causation_id"}), {"task_id": "tasks"}),
    "audit_outbox": (frozenset({"sequence", "event_id", "event_type", "event_version", "actor_id", "principal_type", "correlation_id", "causation_id", "idempotency_key", "payload_json", "created_at", "task_id"}), {"task_id": "tasks"}),
    "flow_runs": (frozenset({"id", "task_id", "flow_id", "flow_version", "flow_hash", "routing_reason", "state", "current_stage_id", "schema_version"}), {"task_id": "tasks"}),
    "stage_runs": (frozenset({"id", "flow_run_id", "stage_id", "stage_snapshot_json", "role_id", "model_alias", "skills_json", "capability_profile", "state", "ordinal", "budgets_json", "schema_version"}), {"flow_run_id": "flow_runs"}),
    "attempts": (frozenset({"id", "stage_run_id", "runtime", "started_at", "input_tokens", "output_tokens", "tool_tokens", "cost_usd", "native_session_id", "herdr_session_id", "finished_at", "failure_class", "exit_result", "schema_version"}), {"stage_run_id": "stage_runs"}),
    "decision_requests": (frozenset({"id", "task_id", "question", "options_json", "evidence_json", "impact", "requested_by", "resolution", "schema_version"}), {"task_id": "tasks"}),
    "approval_requests": (frozenset({"id", "task_id", "action_payload_hash", "scope", "risk", "reason", "expires_at", "nonce", "signer_id", "used_at", "use_event_id", "schema_version"}), {"task_id": "tasks"}),
    "session_links": (frozenset({"id", "task_id", "stage_run_id", "attempt_id", "runtime", "native_session_id", "herdr_session_id", "sanitized_export_artifact_id", "schema_version"}), {"task_id": "tasks", "stage_run_id": "stage_runs", "attempt_id": "attempts"}),
    "handoff_packets": (frozenset({"id", "task_id", "outcome", "changed_files_json", "tests_json", "decisions_json", "risks_json", "unresolved_questions_json", "next_action", "commit_id", "commit_ids_json", "schema_version"}), {"task_id": "tasks"}),
    "artifacts": (frozenset({"id", "task_id", "kind", "uri", "digest", "byte_size", "redaction_class", "retention", "producer", "schema_version"}), {"task_id": "tasks"}),
    "knowledge_syncs": (frozenset({"id", "task_id", "canonical_commit", "state", "ready_for_cleanup", "qmd_receipt", "qmd_collection", "qmd_source_commit", "openviking_receipt", "openviking_uri", "openviking_source_commit", "schema_version"}), {"task_id": "tasks"}),
    "cleanup_records": (frozenset({"id", "task_id", "target_labels_json", "preconditions_json", "actions_json", "verified", "state", "failure_reason", "schema_version"}), {"task_id": "tasks"}),
    "audit_events": (frozenset({"id", "sequence", "event_type", "event_version", "actor_id", "correlation_id", "payload_json", "prior_hash", "event_hash", "occurred_at", "task_id", "causation_id", "schema_version"}), {"task_id": "tasks"}),
}
_PRIMARY_KEYS: Final[dict[str, str]] = {
    "tasks": "id", "idempotency_records": "key", "audit_outbox": "sequence", "flow_runs": "id",
    "stage_runs": "id", "attempts": "id", "decision_requests": "id", "approval_requests": "id",
    "session_links": "id", "handoff_packets": "id", "artifacts": "id", "knowledge_syncs": "id",
    "cleanup_records": "id", "audit_events": "id",
}
_NULLABLE_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "tasks": frozenset(),
    "idempotency_records": frozenset(),
    "audit_outbox": frozenset({"causation_id", "task_id"}),
    "flow_runs": frozenset(),
    "stage_runs": frozenset(),
    "attempts": frozenset({"native_session_id", "herdr_session_id", "finished_at", "failure_class", "exit_result"}),
    "decision_requests": frozenset({"resolution"}),
    "approval_requests": frozenset({"signer_id", "used_at", "use_event_id"}),
    "session_links": frozenset({"native_session_id", "herdr_session_id", "sanitized_export_artifact_id"}),
    "handoff_packets": frozenset({"commit_id"}),
    "artifacts": frozenset(),
    "knowledge_syncs": frozenset({"qmd_receipt", "qmd_collection", "qmd_source_commit", "openviking_receipt", "openviking_uri", "openviking_source_commit"}),
    "cleanup_records": frozenset({"failure_reason"}),
    "audit_events": frozenset({"task_id", "causation_id"}),
}
_INTEGER_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "tasks": frozenset({"version", "schema_version"}),
    "idempotency_records": frozenset(),
    "audit_outbox": frozenset({"sequence", "event_version"}),
    "flow_runs": frozenset({"flow_version", "schema_version"}),
    "stage_runs": frozenset({"ordinal", "schema_version"}),
    "attempts": frozenset({"input_tokens", "output_tokens", "tool_tokens", "schema_version"}),
    "decision_requests": frozenset({"schema_version"}),
    "approval_requests": frozenset({"schema_version"}),
    "session_links": frozenset({"schema_version"}),
    "handoff_packets": frozenset({"schema_version"}),
    "artifacts": frozenset({"byte_size", "schema_version"}),
    "knowledge_syncs": frozenset({"ready_for_cleanup", "schema_version"}),
    "cleanup_records": frozenset({"verified", "schema_version"}),
    "audit_events": frozenset({"sequence", "event_version", "schema_version"}),
}
_REAL_COLUMNS: Final[dict[str, frozenset[str]]] = {
    **{table: frozenset() for table in _TABLE_SPECS},
    "attempts": frozenset({"cost_usd"}),
}


def redact(value: object) -> object:
    """Recursively remove sensitive values before any payload is persisted."""
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _TOKEN_VALUE.sub(_REDACTED, _BEARER_VALUE.sub("Bearer " + _REDACTED, value))
    return value


class SQLiteStore:
    """Own a local SQLite control-plane database and its forward migrations."""

    def __init__(self, path: Path, *, schema_dir: Path | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_dir = schema_dir or _SCHEMA_DIR
        self._connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._enable_wal()
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._apply_migrations()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the SQLite connection owned by this store."""
        self._connection.close()

    def _enable_wal(self) -> None:
        for _ in range(100):
            try:
                self._connection.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower():
                    raise
                time.sleep(0.01)
        raise sqlite3.OperationalError("database remained locked while enabling WAL")

    def create_task(
        self,
        key: str,
        payload: dict[str, str],
        *,
        actor_id: str,
        principal_type: str = "system",
        correlation_id: str,
        causation_id: str,
    ) -> dict[str, str]:
        """Create an intake task once for an idempotency key and canonical request body."""
        actor_id = ensure_uuid7(actor_id)
        correlation_id = ensure_uuid7(correlation_id)
        causation_id = ensure_uuid7(causation_id)
        canonical_payload = self._canonical_json(payload)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT payload_json, task_id, response_json, actor_id, principal_type, correlation_id, causation_id "
                "FROM idempotency_records WHERE key = ?", (key,)
            ).fetchone()
            if existing is not None:
                if existing[0] != canonical_payload:
                    raise ValueError("idempotency key reused with different payload")
                if tuple(existing[3:]) != (actor_id, principal_type, correlation_id, causation_id):
                    raise ValueError("idempotency key reused with different metadata")
                response = self._decode_response(str(existing[2]), str(existing[1]))
                task = self._connection.execute(
                    "SELECT id FROM tasks WHERE id = ?", (str(existing[1]),)
                ).fetchone()
                if task is None or task[0] != response["task_id"]:
                    raise ValueError("idempotency record integrity error")
                return response

            task_id = new_uuid7()
            response = {"task_id": task_id, "state": "intake"}
            occurred_at = datetime.now(UTC).isoformat()
            response_json = self._canonical_json(response)
            self._connection.execute(
                "INSERT INTO tasks (id, payload_json, state, version, schema_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, canonical_payload, "intake", 1, 1, occurred_at),
            )
            self._after_task_insert()
            self._connection.execute(
                "INSERT INTO idempotency_records "
                "(key, payload_json, task_id, response_json, created_at, actor_id, principal_type, correlation_id, causation_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, canonical_payload, task_id, response_json, occurred_at, actor_id, principal_type, correlation_id, causation_id),
            )
            request = payload.get("request", "")
            event_payload = self._canonical_json({"task_id": task_id, "state": "intake", "request_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(), "request_length": len(request)})
            self._connection.execute(
                "INSERT INTO audit_outbox "
                "(event_id, event_type, event_version, actor_id, principal_type, correlation_id, "
                "causation_id, idempotency_key, payload_json, created_at, task_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_uuid7(), "task.created", 1, actor_id, principal_type,
                    correlation_id, causation_id, key, event_payload, occurred_at, task_id,
                ),
            )
            return response

    def count_tasks(self) -> int:
        """Return the number of persisted tasks."""
        return int(self._connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])

    def count_idempotency_records(self) -> int:
        """Return the idempotency record count for transaction assertions."""
        return int(self._connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0])

    def count_outbox_events(self) -> int:
        """Return the outbox count; a read-only helper used to assert transaction behavior."""
        return int(self._connection.execute("SELECT COUNT(*) FROM audit_outbox").fetchone()[0])

    def pragma(self, name: str) -> object:
        """Return a SQLite pragma value for read-only store verification."""
        if name not in {"journal_mode", "foreign_keys", "synchronous"}:
            raise ValueError("unsupported pragma")
        return self._connection.execute(f"PRAGMA {name}").fetchone()[0]

    def applied_migrations(self) -> tuple[str, ...]:
        """Return migration names in application order."""
        rows = self._connection.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def outbox_events(self) -> tuple[dict[str, object], ...]:
        """Return full read-only outbox records for audit-event handoff assertions."""
        rows = self._connection.execute(
            "SELECT event_id, event_type, event_version, actor_id, principal_type, correlation_id, "
            "causation_id, idempotency_key, payload_json, created_at, task_id "
            "FROM audit_outbox ORDER BY sequence"
        ).fetchall()
        return tuple(
            {
                "event_id": str(row[0]), "type": str(row[1]), "event_version": int(row[2]),
                "actor_id": str(row[3]), "principal_type": str(row[4]),
                "correlation_id": str(row[5]), "causation_id": row[6],
                "idempotency_key": str(row[7]), "payload": cast(dict[str, object], json.loads(str(row[8]))),
                "occurred_at": str(row[9]), "task_id": row[10],
            }
            for row in rows
        )

    def _after_task_insert(self) -> None:
        """Provide a failure-injection seam between task and outbox writes."""

    def _apply_migrations(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(filename TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        migrations = sorted(self._schema_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            has_applied_migrations = self._connection.execute(
                "SELECT 1 FROM schema_migrations LIMIT 1"
            ).fetchone() is not None
            if not has_applied_migrations:
                self._validate_existing_schema()
            for migration in migrations:
                filename = migration.stem
                script = migration.read_text(encoding="utf-8")
                checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()
                applied = self._connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE filename = ?", (filename,)
                ).fetchone()
                if applied is not None:
                    if applied[0] != checksum:
                        raise ValueError(f"migration drift detected for {filename}")
                    continue
                self._execute_migration_script(script)
                self._connection.execute(
                    "INSERT INTO schema_migrations (filename, checksum, applied_at) VALUES (?, ?, ?)",
                    (filename, checksum, datetime.now(UTC).isoformat()),
                )
            self._validate_existing_schema(require_all=True)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self._validate_existing_schema(require_all=True)

    def _validate_existing_schema(self, *, require_all: bool = False) -> None:
        for table, (required_columns, expected_foreign_keys) in _TABLE_SPECS.items():
            row = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if row is None:
                if require_all:
                    raise ValueError(f"migration schema mismatch: missing {table}")
                continue
            column_details = {
                str(item[1]): (str(item[2]).upper(), int(item[3]), int(item[5]))
                for item in self._connection.execute(f"PRAGMA table_info({table})")
            }
            columns = set(column_details)
            if not required_columns.issubset(columns):
                raise ValueError(f"migration schema mismatch: {table}")
            primary_key = _PRIMARY_KEYS[table]
            required_not_null = required_columns - _NULLABLE_COLUMNS[table] - {primary_key}
            if column_details[primary_key][2] != 1 or any(
                column_details[column][1] != 1 for column in required_not_null
            ):
                raise ValueError(f"migration constraint mismatch: {table}")
            if any(column_details[column][1] != 0 for column in _NULLABLE_COLUMNS[table]):
                raise ValueError(f"migration constraint mismatch: {table}")
            expected_types = {
                column: "INTEGER" if column in _INTEGER_COLUMNS[table]
                else "REAL" if column in _REAL_COLUMNS[table]
                else "TEXT"
                for column in required_columns
            }
            if any(column_details[column][0] != expected_type for column, expected_type in expected_types.items()):
                raise ValueError(f"migration type mismatch: {table}")
            foreign_keys = {
                str(item[3]): (str(item[2]), str(item[4]), str(item[5]), str(item[6]))
                for item in self._connection.execute(f"PRAGMA foreign_key_list({table})")
            }
            expected_fk_details = {
                child: (parent, "id", "NO ACTION", "NO ACTION")
                for child, parent in expected_foreign_keys.items()
            }
            if foreign_keys != expected_fk_details:
                raise ValueError(f"migration foreign key mismatch: {table}")

    def _execute_migration_script(self, script: str) -> None:
        statement = ""
        for line in script.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                if statement.strip():
                    self._connection.execute(statement)
                statement = ""
        if statement.strip():
            raise ValueError("incomplete migration statement")

    @staticmethod
    def _canonical_json(value: Mapping[str, object]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode_response(value: str, expected_task_id: str) -> dict[str, str]:
        try:
            response = cast(dict[str, str], json.loads(value))
            task_id = ensure_uuid7(response["task_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("idempotency record integrity error") from error
        if task_id != expected_task_id or response != {"task_id": task_id, "state": "intake"}:
            raise ValueError("idempotency record integrity error")
        return response
