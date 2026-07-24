"""HMAC-signed canonical JSON and one-use approval consumption.

Principal assertions and approval payloads are signed with HMAC-SHA256 over compact,
sorted-key JSON so the signature is stable regardless of field ordering. Approval
consumption delegates the actual one-use claim to ``SQLiteStore.use_approval_request``,
which performs the atomic check-and-set; this module adds the digest, expiry, and
not-found checks around that atomic core so a replay is rejected before or after the
race, never silently accepted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime


class ApprovalError(RuntimeError):
    """Base class for approval-flow failures. ``code`` maps to the stable error contract."""

    code = "policy_denied"


class ApprovalNotFoundError(ApprovalError):
    code = "not_found"


class ApprovalExpiredError(ApprovalError):
    code = "approval_expired"


class ApprovalReplayedError(ApprovalError):
    code = "approval_replayed"


class ApprovalDigestMismatchError(ApprovalError):
    code = "validation_failed"


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    task_id: str
    action_payload_hash: str
    scope: str
    risk: str
    reason: str
    expires_at: datetime
    nonce: str


def canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def sign(secret: bytes, payload: bytes) -> str:
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_signature(secret: bytes, payload: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(secret, payload), signature)


def _parse_expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _to_record(row: Mapping[str, object]) -> ApprovalRecord:
    return ApprovalRecord(
        id=str(row["id"]),
        task_id=str(row["task_id"]),
        action_payload_hash=str(row["action_payload_hash"]),
        scope=str(row["scope"]),
        risk=str(row["risk"]),
        reason=str(row["reason"]),
        expires_at=_parse_expiry(str(row["expires_at"])),
        nonce=str(row["nonce"]),
    )


def reject(
    store: object,
    approval_id: str,
    *,
    actor_id: str,
    use_event_id: str,
    now: datetime,
) -> ApprovalRecord:
    """Verify and one-use-consume an approval as a rejection (no action-payload digest check)."""
    row = store.get_approval_request(approval_id)  # type: ignore[attr-defined]
    if row is None:
        raise ApprovalNotFoundError(f"unknown approval: {approval_id}")
    if row["used_at"] is not None:
        raise ApprovalReplayedError(f"approval already used: {approval_id}")
    record = _to_record(row)
    if now > record.expires_at:
        raise ApprovalExpiredError(f"approval expired: {approval_id}")
    claimed = store.use_approval_request(  # type: ignore[attr-defined]
        approval_id,
        use_event_id=use_event_id,
        signer_id=actor_id,
        used_at=now.isoformat(),
    )
    if not claimed:
        raise ApprovalReplayedError(f"approval already used: {approval_id}")
    return record


def consume(
    store: object,
    approval_id: str,
    action_payload: Mapping[str, object],
    *,
    actor_id: str,
    use_event_id: str,
    now: datetime,
) -> ApprovalRecord:
    """Verify and one-use-consume an approval. Raises a typed ``ApprovalError`` on any failure.

    ``store`` is an ``aegis.storage.sqlite.SQLiteStore``; typed loosely here to avoid a
    hard import cycle between the policy and storage packages.
    """
    row = store.get_approval_request(approval_id)  # type: ignore[attr-defined]
    if row is None:
        raise ApprovalNotFoundError(f"unknown approval: {approval_id}")
    if row["used_at"] is not None:
        raise ApprovalReplayedError(f"approval already used: {approval_id}")
    record = _to_record(row)
    if now > record.expires_at:
        raise ApprovalExpiredError(f"approval expired: {approval_id}")
    if digest(action_payload) != record.action_payload_hash:
        raise ApprovalDigestMismatchError("action payload does not match the approved action")
    claimed = store.use_approval_request(  # type: ignore[attr-defined]
        approval_id,
        use_event_id=use_event_id,
        signer_id=actor_id,
        used_at=now.isoformat(),
    )
    if not claimed:
        raise ApprovalReplayedError(f"approval already used: {approval_id}")
    return record
