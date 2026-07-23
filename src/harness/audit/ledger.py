"""Append-only JSONL audit ledger and transactional-outbox flusher."""

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Final, cast

from harness.audit.redaction import redact
from harness.domain.ids import new_uuid7

if TYPE_CHECKING:
    from harness.storage.sqlite import SQLiteStore

_GENESIS_HASH: Final = "0" * 64
_MANIFEST_SUFFIX: Final = ".manifest"


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"audit {field} must be an integer")
    return value


class Ledger:
    """A local, redacted JSONL hash chain with a durable terminal manifest."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._manifest_path = path.with_name(path.name + _MANIFEST_SUFFIX)
        self._lock = RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: Mapping[str, object]) -> dict[str, object]:
        """Append one local event, redacting it before it receives a hash."""
        return self._append(
            {
                "event_id": new_uuid7(),
                "event_type": event_type,
                "event_version": 1,
                "actor_id": new_uuid7(),
                "correlation_id": new_uuid7(),
                "causation_id": None,
                "task_id": None,
                "occurred_at": datetime.now(UTC).isoformat(),
                "payload": dict(payload),
            }
        )

    def append_outbox(self, event: Mapping[str, object]) -> dict[str, object]:
        """Append an already committed outbox event exactly once by sequence."""
        required = {
            "sequence",
            "event_id",
            "event_type",
            "event_version",
            "actor_id",
            "correlation_id",
            "causation_id",
            "task_id",
            "created_at",
            "payload",
        }
        missing = required - set(event)
        if missing:
            raise ValueError(f"outbox event is missing fields: {sorted(missing)}")
        return self._append(
            {
                "sequence": event["sequence"],
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "event_version": event["event_version"],
                "actor_id": event["actor_id"],
                "correlation_id": event["correlation_id"],
                "causation_id": event["causation_id"],
                "task_id": event["task_id"],
                "occurred_at": event["created_at"],
                "payload": event["payload"],
            }
        )

    def verify(self) -> list[int]:
        """Return the first corrupt or missing sequence, or an empty list when valid."""
        with self._lock:
            records, malformed_sequence = self._read_records()
            if malformed_sequence is not None:
                return [malformed_sequence]
            mismatch = self._verify_records(records)
            if mismatch is not None:
                return [mismatch]
            manifest_mismatch = self._manifest_mismatch(records)
            if manifest_mismatch is not None:
                return [manifest_mismatch]
            return []

    def _append(self, source: Mapping[str, object]) -> dict[str, object]:
        with self._lock:
            records, malformed_sequence = self._read_records()
            if malformed_sequence is not None:
                raise ValueError(f"audit ledger is malformed at sequence {malformed_sequence}")
            mismatch = self._verify_records(records)
            if mismatch is not None:
                raise ValueError(f"audit ledger integrity failure at sequence {mismatch}")
            manifest_mismatch = self._manifest_mismatch(records)
            if manifest_mismatch is not None:
                raise ValueError(f"audit manifest integrity failure at sequence {manifest_mismatch}")
            next_sequence = _integer(records[-1]["sequence"], "sequence") + 1 if records else 1
            expected_sequence = _integer(source.get("sequence", next_sequence), "sequence")
            payload = redact(source["payload"])
            existing = next(
                (
                    record
                    for record in records
                    if _integer(record["sequence"], "sequence") == expected_sequence
                ),
                None,
            )
            prior_hash = (
                str(existing["prior_hash"])
                if existing is not None
                else str(records[-1]["event_hash"]) if records else _GENESIS_HASH
            )
            candidate = {
                "sequence": expected_sequence,
                "event_id": str(source["event_id"]),
                "event_type": str(source["event_type"]),
                "event_version": _integer(source["event_version"], "event_version"),
                "actor_id": str(source["actor_id"]),
                "correlation_id": str(source["correlation_id"]),
                "causation_id": source["causation_id"],
                "task_id": source["task_id"],
                "occurred_at": str(source["occurred_at"]),
                "payload": payload,
                "prior_hash": prior_hash,
            }
            candidate["event_hash"] = self._hash(candidate)
            if existing is not None:
                if self._canonical_json(existing) != self._canonical_json(candidate):
                    raise ValueError("audit sequence was already written with different content")
                self._write_manifest(existing)
                return existing
            if expected_sequence != next_sequence:
                raise ValueError("audit sequence is not contiguous")
            self._append_line(candidate)
            self._write_manifest(candidate)
            return candidate

    def _read_records(self) -> tuple[list[dict[str, object]], int | None]:
        if not self._path.exists():
            return [], None
        records: list[dict[str, object]] = []
        for line_number, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return records, line_number
            if not isinstance(value, dict):
                return records, line_number
            records.append(cast(dict[str, object], value))
        return records, None

    def _verify_records(self, records: list[dict[str, object]]) -> int | None:
        prior_hash = _GENESIS_HASH
        expected_sequence = 1
        for record in records:
            sequence = record.get("sequence")
            if not isinstance(sequence, int) or sequence != expected_sequence:
                return expected_sequence
            if record.get("prior_hash") != prior_hash or record.get("payload") != redact(record.get("payload")):
                return sequence
            if record.get("event_hash") != self._hash(record):
                return sequence
            prior_hash = str(record["event_hash"])
            expected_sequence += 1
        return None

    @staticmethod
    def _hash(record: Mapping[str, object]) -> str:
        material = {
            "actor_id": record["actor_id"],
            "causation_id": record["causation_id"],
            "correlation_id": record["correlation_id"],
            "event_id": record["event_id"],
            "event_type": record["event_type"],
            "event_version": record["event_version"],
            "occurred_at": record["occurred_at"],
            "payload": record["payload"],
            "prior_hash": record["prior_hash"],
            "sequence": record["sequence"],
            "task_id": record["task_id"],
        }
        return hashlib.sha256(Ledger._canonical_json(material).encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _append_line(self, event: Mapping[str, object]) -> None:
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(self._canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _read_manifest(self) -> dict[str, object] | None:
        if not self._manifest_path.exists():
            return None
        try:
            value = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"invalid": True}
        return cast(dict[str, object], value) if isinstance(value, dict) else {"invalid": True}

    def _manifest_mismatch(self, records: list[dict[str, object]]) -> int | None:
        manifest = self._read_manifest()
        if not records:
            return None if manifest is None else 1
        sequence = _integer(records[-1]["sequence"], "sequence")
        event_hash = str(records[-1]["event_hash"])
        if manifest != {"sequence": sequence, "event_hash": event_hash}:
            return sequence + 1
        return None

    def _write_manifest(self, event: Mapping[str, object]) -> None:
        payload = self._canonical_json(
            {"sequence": _integer(event["sequence"], "sequence"), "event_hash": str(event["event_hash"])}
        )
        with self._manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def flush_outbox(store: "SQLiteStore", ledger: Ledger, *, claimer_id: str, limit: int = 100) -> int:
    """Append the ordered committed outbox prefix and durably mark each event flushed."""
    events = store.claim_outbox_events(claimer_id, limit=limit)
    flushed = 0
    for event in events:
        try:
            written = ledger.append_outbox(event)
            if store.mark_outbox_flushed(_integer(event["sequence"], "sequence"), claimer_id, written):
                flushed += 1
        except Exception:
            store.release_outbox_claim(_integer(event["sequence"], "sequence"), claimer_id)
            raise
    return flushed
