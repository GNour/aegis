"""Append-only JSONL audit ledger, durable segments, and outbox flushing."""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Final, Iterator, cast

from harness.audit.redaction import redact
from harness.domain.ids import new_uuid7

if TYPE_CHECKING:
    from harness.storage.sqlite import SQLiteStore

Signer = Callable[[bytes], str]
Verifier = Callable[[bytes, str], bool]

_GENESIS_HASH: Final = "0" * 64
_MANIFEST_SUFFIX: Final = ".manifest"
_CHECKPOINT_SUFFIX: Final = ".checkpoint"
_ROTATION_SUFFIX: Final = ".rotation"
_LOCK_SUFFIX: Final = ".lock"
_SEGMENT_VERSION: Final = 1
_EVENT_FIELDS: Final = frozenset(
    {
        "sequence",
        "event_id",
        "event_type",
        "event_version",
        "actor_id",
        "correlation_id",
        "causation_id",
        "task_id",
        "occurred_at",
        "payload",
        "prior_hash",
        "event_hash",
    }
)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"audit {field} must be an integer")
    return value


@dataclass(frozen=True)
class _LedgerState:
    terminal_sequence: int
    terminal_hash: str
    active_start_sequence: int
    active_prior_hash: str


class Ledger:
    """Redacted JSONL hash chain with crash-safe manifests and signed segments."""

    def __init__(
        self, path: Path, *, signer: Signer | None = None, verifier: Verifier | None = None
    ) -> None:
        self._path = path
        self._manifest_path = path.with_name(path.name + _MANIFEST_SUFFIX)
        self._checkpoint_path = path.with_name(path.name + _CHECKPOINT_SUFFIX)
        self._rotation_path = path.with_name(path.name + _ROTATION_SUFFIX)
        self._lock_path = path.with_name(path.name + _LOCK_SUFFIX)
        self._signer = signer
        self._verifier = verifier
        self._lock = RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._file_lock():
            self._recover_rotation()
            self._load_verified(reconcile_manifest=True)

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
        """Append an already committed outbox event exactly once by global sequence."""
        required = {
            "sequence", "event_id", "event_type", "event_version", "actor_id", "correlation_id",
            "causation_id", "task_id", "created_at", "payload",
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

    def rotate(self) -> Path:
        """Seal the active segment with a signed manifest and start its successor."""
        if self._signer is None:
            raise ValueError("audit rotation requires a segment manifest signer")
        if self._verifier is None:
            raise ValueError("audit rotation requires a segment manifest verifier")
        with self._lock, self._file_lock():
            records, state = self._load_verified(reconcile_manifest=True)
            if not records:
                raise ValueError("cannot rotate an empty audit segment")
            terminal_sequence = _integer(records[-1]["sequence"], "sequence")
            terminal_hash = str(records[-1]["event_hash"])
            segment_path = self._segment_path(state.active_start_sequence, terminal_sequence)
            if segment_path.exists() or self._segment_manifest_path(segment_path).exists():
                raise ValueError("audit segment already exists")
            body = {
                "version": _SEGMENT_VERSION,
                "segment_file": segment_path.name,
                "first_sequence": state.active_start_sequence,
                "terminal_sequence": terminal_sequence,
                "prior_hash": state.active_prior_hash,
                "terminal_hash": terminal_hash,
            }
            signature = self._signer(self._canonical_json(body).encode("utf-8"))
            if not isinstance(signature, str) or not signature:
                raise ValueError("audit segment signer returned an invalid signature")
            target_state = _LedgerState(
                terminal_sequence=terminal_sequence,
                terminal_hash=terminal_hash,
                active_start_sequence=terminal_sequence + 1,
                active_prior_hash=terminal_hash,
            )
            intent = self._rotation_intent(
                "prepared", state, target_state, segment_path, {**body, "signature": signature}
            )
            self._write_rotation_intent(intent)
            self._after_rotation_transition("prepared")
            self._atomic_write_json(self._segment_manifest_path(segment_path), {**body, "signature": signature})
            intent["phase"] = "segment_manifest_written"
            self._write_rotation_intent(intent)
            self._after_rotation_transition("segment_manifest_written")
            os.replace(self._path, segment_path)
            self._fsync_directory()
            intent["phase"] = "active_renamed"
            self._write_rotation_intent(intent)
            self._after_rotation_transition("active_renamed")
            self._path.touch(exist_ok=False)
            self._fsync_file(self._path)
            intent["phase"] = "active_created"
            self._write_rotation_intent(intent)
            self._after_rotation_transition("active_created")
            self._write_state_manifest(target_state)
            self._write_checkpoint(target_state)
            intent["phase"] = "state_written"
            self._write_rotation_intent(intent)
            self._after_rotation_transition("state_written")
            self._remove_rotation_intent()
            return segment_path

    def _after_rotation_transition(self, phase: str) -> None:
        """Provide a fault-injection seam after each durable rotation transition."""

    def _rotation_intent(
        self,
        phase: str,
        source: _LedgerState,
        target: _LedgerState,
        segment_path: Path,
        segment_manifest: Mapping[str, object],
    ) -> dict[str, object]:
        return {
            "phase": phase,
            "segment_file": segment_path.name,
            "source_terminal_sequence": source.terminal_sequence,
            "source_terminal_hash": source.terminal_hash,
            "source_active_start_sequence": source.active_start_sequence,
            "source_active_prior_hash": source.active_prior_hash,
            "target_terminal_sequence": target.terminal_sequence,
            "target_terminal_hash": target.terminal_hash,
            "target_active_start_sequence": target.active_start_sequence,
            "target_active_prior_hash": target.active_prior_hash,
            "segment_manifest": dict(segment_manifest),
        }

    def verify(self) -> list[int]:
        """Return the first bad sequence or file position; never raise for malformed events."""
        with self._lock, self._file_lock():
            try:
                records, malformed_position = self._read_records(self._path)
                if malformed_position is not None:
                    return [malformed_position]
                state = self._read_state(records)
                mismatch = self._verify_records(
                    records, state.active_start_sequence, state.active_prior_hash
                )
                if mismatch is not None:
                    return [mismatch]
                state_mismatch = self._state_mismatch(records, state)
                if state_mismatch is not None:
                    return [state_mismatch]
                return self._verify_segments(state)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return [1]

    def _append(self, source: Mapping[str, object]) -> dict[str, object]:
        with self._lock, self._file_lock():
            records, state = self._load_verified(reconcile_manifest=True)
            next_sequence = _integer(records[-1]["sequence"], "sequence") + 1 if records else state.active_start_sequence
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
                else str(records[-1]["event_hash"]) if records else state.active_prior_hash
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
                return existing
            if expected_sequence != next_sequence:
                raise ValueError("audit sequence is not contiguous")
            self._append_line(candidate)
            updated_state = _LedgerState(
                terminal_sequence=expected_sequence,
                terminal_hash=str(candidate["event_hash"]),
                active_start_sequence=state.active_start_sequence,
                active_prior_hash=state.active_prior_hash,
            )
            self._write_state_manifest(updated_state)
            self._write_checkpoint(updated_state)
            return candidate

    def _load_verified(self, *, reconcile_manifest: bool) -> tuple[list[dict[str, object]], _LedgerState]:
        records, malformed_position = self._read_records(self._path)
        if malformed_position is not None:
            raise ValueError(f"audit ledger is malformed at position {malformed_position}")
        state = self._read_state(records)
        mismatch = self._verify_records(records, state.active_start_sequence, state.active_prior_hash)
        if mismatch is not None:
            raise ValueError(f"audit ledger integrity failure at sequence {mismatch}")
        mismatch = self._state_mismatch(records, state)
        if mismatch is not None:
            if not reconcile_manifest or not self._state_is_safely_stale(records, state):
                raise ValueError(f"audit manifest integrity failure at sequence {mismatch}")
            state = self._state_for_records(records, state)
            self._write_state_manifest(state)
        self._raise_if_segments_invalid(state)
        self._reconcile_checkpoint(state)
        return records, state

    def _recover_rotation(self) -> None:
        intent = self._read_json(self._rotation_path)
        if intent is None:
            return
        source, target, segment_path, segment_manifest = self._parse_rotation_intent(intent)
        if segment_path.exists():
            if not self._segment_manifest_path(segment_path).exists():
                self._atomic_write_json(self._segment_manifest_path(segment_path), segment_manifest)
            if not self._path.exists():
                self._path.touch(exist_ok=False)
                self._fsync_file(self._path)
        elif self._path.exists():
            records, malformed_position = self._read_records(self._path)
            if malformed_position is not None:
                raise ValueError(f"rotation source is malformed at position {malformed_position}")
            mismatch = self._verify_records(
                records, source.active_start_sequence, source.active_prior_hash
            )
            if (
                mismatch is not None
                or not records
                or _integer(records[-1]["sequence"], "sequence") != source.terminal_sequence
                or str(records[-1]["event_hash"]) != source.terminal_hash
            ):
                raise ValueError("rotation source no longer matches its durable intent")
            self._atomic_write_json(self._segment_manifest_path(segment_path), segment_manifest)
            os.replace(self._path, segment_path)
            self._fsync_directory()
            self._path.touch(exist_ok=False)
            self._fsync_file(self._path)
        else:
            raise ValueError("rotation intent has neither an active nor a sealed segment")
        self._write_state_manifest(target)
        self._write_checkpoint(target)
        self._remove_rotation_intent()

    def _parse_rotation_intent(
        self, intent: Mapping[str, object]
    ) -> tuple[_LedgerState, _LedgerState, Path, dict[str, object]]:
        expected = {
            "phase", "segment_file", "source_terminal_sequence", "source_terminal_hash",
            "source_active_start_sequence", "source_active_prior_hash", "target_terminal_sequence",
            "target_terminal_hash", "target_active_start_sequence", "target_active_prior_hash",
            "segment_manifest",
        }
        phases = {
            "prepared", "segment_manifest_written", "active_renamed", "active_created", "state_written"
        }
        if set(intent) != expected or intent["phase"] not in phases:
            raise ValueError("rotation intent has an invalid schema")
        segment_file = intent["segment_file"]
        segment_manifest = intent["segment_manifest"]
        if not isinstance(segment_file, str) or not isinstance(segment_manifest, Mapping):
            raise ValueError("rotation intent has invalid segment metadata")
        source = self._intent_state(intent, "source")
        target = self._intent_state(intent, "target")
        if (
            target.terminal_sequence != source.terminal_sequence
            or target.terminal_hash != source.terminal_hash
            or target.active_start_sequence != source.terminal_sequence + 1
            or target.active_prior_hash != source.terminal_hash
        ):
            raise ValueError("rotation intent has invalid state transition")
        segment_path = self._path.with_name(segment_file)
        if segment_path != self._segment_path(source.active_start_sequence, source.terminal_sequence):
            raise ValueError("rotation intent names an unexpected segment")
        manifest = cast(dict[str, object], dict(segment_manifest))
        body = self._parse_segment_manifest(manifest, segment_path.name)
        if (
            body["first_sequence"] != source.active_start_sequence
            or body["terminal_sequence"] != source.terminal_sequence
            or body["prior_hash"] != source.active_prior_hash
            or body["terminal_hash"] != source.terminal_hash
        ):
            raise ValueError("rotation intent segment does not match source state")
        return source, target, segment_path, manifest

    def _intent_state(self, intent: Mapping[str, object], prefix: str) -> _LedgerState:
        return _LedgerState(
            _integer(intent[f"{prefix}_terminal_sequence"], f"{prefix} terminal sequence"),
            self._hash_text(intent[f"{prefix}_terminal_hash"], f"{prefix} terminal hash"),
            _integer(intent[f"{prefix}_active_start_sequence"], f"{prefix} active start sequence"),
            self._hash_text(intent[f"{prefix}_active_prior_hash"], f"{prefix} active prior hash"),
        )

    def _write_rotation_intent(self, intent: Mapping[str, object]) -> None:
        self._atomic_write_json(self._rotation_path, intent)

    def _remove_rotation_intent(self) -> None:
        self._rotation_path.unlink(missing_ok=True)
        self._fsync_directory()

    def _read_records(self, path: Path) -> tuple[list[dict[str, object]], int | None]:
        if not path.exists():
            return [], None
        records: list[dict[str, object]] = []
        for position, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return records, position
            if not isinstance(value, dict):
                return records, position
            records.append(cast(dict[str, object], value))
        return records, None

    def _read_state(self, records: list[dict[str, object]]) -> _LedgerState:
        manifest = self._read_json(self._manifest_path)
        if manifest is None:
            terminal_sequence, terminal_hash = self._sealed_segment_tail()
            active_start_sequence = terminal_sequence + 1
            if records and _integer(records[0].get("sequence"), "sequence") != active_start_sequence:
                raise ValueError("missing audit manifest cannot establish segment boundary")
            return _LedgerState(
                terminal_sequence, terminal_hash, active_start_sequence, terminal_hash
            )
        if set(manifest) == {"sequence", "event_hash"}:
            terminal_sequence = _integer(manifest["sequence"], "sequence")
            terminal_hash = self._hash_text(manifest["event_hash"], "event_hash")
            return _LedgerState(terminal_sequence, terminal_hash, 1, _GENESIS_HASH)
        expected = {
            "terminal_sequence", "terminal_hash", "active_start_sequence", "active_prior_hash"
        }
        if set(manifest) != expected:
            raise ValueError("audit manifest has an invalid schema")
        return _LedgerState(
            _integer(manifest["terminal_sequence"], "terminal_sequence"),
            self._hash_text(manifest["terminal_hash"], "terminal_hash"),
            _integer(manifest["active_start_sequence"], "active_start_sequence"),
            self._hash_text(manifest["active_prior_hash"], "active_prior_hash"),
        )

    def _reconcile_checkpoint(self, state: _LedgerState) -> None:
        checkpoint = self._read_json(self._checkpoint_path)
        if checkpoint is None:
            self._write_checkpoint(state)
            return
        if set(checkpoint) != {"sequence", "event_hash"}:
            raise ValueError("audit checkpoint has an invalid schema")
        sequence = _integer(checkpoint["sequence"], "checkpoint sequence")
        event_hash = self._hash_text(checkpoint["event_hash"], "checkpoint event_hash")
        if sequence > state.terminal_sequence:
            raise ValueError("audit checkpoint is ahead of the verified ledger")
        if sequence == state.terminal_sequence and event_hash != state.terminal_hash:
            raise ValueError("audit checkpoint terminal hash mismatch")
        if sequence < state.terminal_sequence:
            self._write_checkpoint(state)

    def _write_checkpoint(self, state: _LedgerState) -> None:
        self._atomic_write_json(
            self._checkpoint_path,
            {"sequence": state.terminal_sequence, "event_hash": state.terminal_hash},
        )

    def _state_mismatch(self, records: list[dict[str, object]], state: _LedgerState) -> int | None:
        actual = self._state_for_records(records, state)
        if actual.terminal_sequence == state.terminal_sequence and actual.terminal_hash == state.terminal_hash:
            return None
        return actual.terminal_sequence + 1

    def _state_is_safely_stale(self, records: list[dict[str, object]], state: _LedgerState) -> bool:
        actual = self._state_for_records(records, state)
        if state.terminal_sequence > actual.terminal_sequence:
            return False
        if state.terminal_sequence == state.active_start_sequence - 1:
            return state.terminal_hash == state.active_prior_hash
        for record in records:
            if _integer(record["sequence"], "sequence") == state.terminal_sequence:
                return str(record["event_hash"]) == state.terminal_hash
        return False

    @staticmethod
    def _state_for_records(records: list[dict[str, object]], state: _LedgerState) -> _LedgerState:
        if not records:
            return state
        return _LedgerState(
            terminal_sequence=_integer(records[-1]["sequence"], "sequence"),
            terminal_hash=str(records[-1]["event_hash"]),
            active_start_sequence=state.active_start_sequence,
            active_prior_hash=state.active_prior_hash,
        )

    @staticmethod
    def _verify_records(
        records: list[dict[str, object]], expected_sequence: int, prior_hash: str
    ) -> int | None:
        for position, record in enumerate(records, start=expected_sequence):
            sequence = record.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence != expected_sequence:
                return sequence if isinstance(sequence, int) and sequence > 0 else position
            if set(record) != _EVENT_FIELDS or not Ledger._event_has_valid_types(record):
                return sequence
            if record["prior_hash"] != prior_hash or record["payload"] != redact(record["payload"]):
                return sequence
            if record["event_hash"] != Ledger._hash(record):
                return sequence
            prior_hash = str(record["event_hash"])
            expected_sequence += 1
        return None

    @staticmethod
    def _event_has_valid_types(record: Mapping[str, object]) -> bool:
        return (
            isinstance(record["event_id"], str)
            and isinstance(record["event_type"], str)
            and isinstance(record["event_version"], int)
            and not isinstance(record["event_version"], bool)
            and int(record["event_version"]) > 0
            and isinstance(record["actor_id"], str)
            and isinstance(record["correlation_id"], str)
            and isinstance(record["occurred_at"], str)
            and isinstance(record["payload"], Mapping)
            and isinstance(record["prior_hash"], str)
            and isinstance(record["event_hash"], str)
            and (record["task_id"] is None or isinstance(record["task_id"], str))
            and (record["causation_id"] is None or isinstance(record["causation_id"], str))
        )

    def _verify_segments(self, active_state: _LedgerState) -> list[int]:
        try:
            self._raise_if_segments_invalid(active_state)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return [active_state.active_start_sequence]
        return []

    def _raise_if_segments_invalid(self, active_state: _LedgerState) -> None:
        terminal_sequence, prior_hash = self._sealed_segment_tail()
        if (
            active_state.active_start_sequence != terminal_sequence + 1
            or active_state.active_prior_hash != prior_hash
        ):
            raise ValueError("audit active segment does not link to the sealed segment")

    def _sealed_segment_tail(self) -> tuple[int, str]:
        prior_hash = _GENESIS_HASH
        terminal_sequence = 0
        for segment_path in sorted(self._path.parent.glob(self._path.name + ".*.jsonl")):
            manifest = self._read_json(self._segment_manifest_path(segment_path))
            if manifest is None:
                raise ValueError("audit segment is missing its manifest")
            body = self._parse_segment_manifest(manifest, segment_path.name)
            if body["first_sequence"] != terminal_sequence + 1 or body["prior_hash"] != prior_hash:
                raise ValueError("audit segment chain mismatch")
            records, malformed_position = self._read_records(segment_path)
            if malformed_position is not None:
                raise ValueError(f"audit segment is malformed at position {malformed_position}")
            mismatch = self._verify_records(
                records, _integer(body["first_sequence"], "first_sequence"), str(body["prior_hash"])
            )
            if mismatch is not None or not records:
                raise ValueError("audit segment event chain mismatch")
            if (
                _integer(records[-1]["sequence"], "sequence") != body["terminal_sequence"]
                or str(records[-1]["event_hash"]) != body["terminal_hash"]
            ):
                raise ValueError("audit segment terminal mismatch")
            terminal_sequence = _integer(body["terminal_sequence"], "terminal_sequence")
            prior_hash = str(body["terminal_hash"])
        return terminal_sequence, prior_hash

    def _parse_segment_manifest(
        self, manifest: Mapping[str, object], expected_file: str
    ) -> dict[str, object]:
        expected = {
            "version", "segment_file", "first_sequence", "terminal_sequence", "prior_hash", "terminal_hash", "signature"
        }
        if set(manifest) != expected or manifest["segment_file"] != expected_file:
            raise ValueError("audit segment manifest has an invalid schema")
        body = {key: value for key, value in manifest.items() if key != "signature"}
        if _integer(body["version"], "segment version") != _SEGMENT_VERSION:
            raise ValueError("unsupported audit segment version")
        first = _integer(body["first_sequence"], "first_sequence")
        terminal = _integer(body["terminal_sequence"], "terminal_sequence")
        if first < 1 or terminal < first:
            raise ValueError("audit segment has invalid sequence bounds")
        self._hash_text(body["prior_hash"], "prior_hash")
        self._hash_text(body["terminal_hash"], "terminal_hash")
        signature = manifest["signature"]
        if not isinstance(signature, str) or self._verifier is None:
            raise ValueError("audit segment signature cannot be verified")
        if not self._verifier(self._canonical_json(body).encode("utf-8"), signature):
            raise ValueError("audit segment signature is invalid")
        return body

    @staticmethod
    def _hash_text(value: object, field: str) -> str:
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"audit {field} must be a lowercase SHA-256 hash")
        return value

    @staticmethod
    def _hash(record: Mapping[str, object]) -> str:
        material = {
            "actor_id": record["actor_id"], "causation_id": record["causation_id"],
            "correlation_id": record["correlation_id"], "event_id": record["event_id"],
            "event_type": record["event_type"], "event_version": record["event_version"],
            "occurred_at": record["occurred_at"], "payload": record["payload"],
            "prior_hash": record["prior_hash"], "sequence": record["sequence"], "task_id": record["task_id"],
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

    def _read_json(self, path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("audit manifest must be a JSON object")
        return cast(dict[str, object], value)

    def _write_state_manifest(self, state: _LedgerState) -> None:
        self._atomic_write_json(
            self._manifest_path,
            {
                "terminal_sequence": state.terminal_sequence,
                "terminal_hash": state.terminal_hash,
                "active_start_sequence": state.active_start_sequence,
                "active_prior_hash": state.active_prior_hash,
            },
        )

    def _atomic_write_json(self, path: Path, value: Mapping[str, object]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._canonical_json(value) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            self._fsync_directory()
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _fsync_file(self, path: Path) -> None:
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())

    def _fsync_directory(self) -> None:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            return
        descriptor = os.open(self._path.parent, os.O_RDONLY | directory_flag)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _segment_path(self, first_sequence: int, terminal_sequence: int) -> Path:
        return self._path.with_name(
            f"{self._path.name}.{first_sequence:020d}-{terminal_sequence:020d}.jsonl"
        )

    @staticmethod
    def _segment_manifest_path(segment_path: Path) -> Path:
        return segment_path.with_name(segment_path.name + _MANIFEST_SUFFIX)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        with self._lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                getattr(fcntl, "flock")(handle.fileno(), getattr(fcntl, "LOCK_EX"))
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    getattr(fcntl, "flock")(handle.fileno(), getattr(fcntl, "LOCK_UN"))


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
