"""Signed principal assertions (spec 01 section 4).

Every request carries a short-lived, HMAC-SHA256-signed assertion naming the actor,
interface, allowed operation, issue/expiry time, a nonce, and a digest of the request
body. ``decode_and_verify`` validates all five properties — signature, expiry, nonce
replay, operation match, and body digest — and rejects on the first failure. Assertions
are never logged or forwarded to workers; callers should redact the raw header value.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from aegis.policy.approvals import canonical_json, sign, verify_signature


class AuthError(RuntimeError):
    """Raised for any assertion failure. Maps to the stable ``unauthorized`` error code."""

    code = "unauthorized"


@dataclass(frozen=True)
class PrincipalAssertion:
    actor_id: str
    principal_type: str
    interface: str
    operation: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    body_sha256: str


def _assertion_payload(assertion: PrincipalAssertion) -> dict[str, object]:
    return {
        "actor_id": assertion.actor_id,
        "principal_type": assertion.principal_type,
        "interface": assertion.interface,
        "operation": assertion.operation,
        "issued_at": assertion.issued_at.isoformat(),
        "expires_at": assertion.expires_at.isoformat(),
        "nonce": assertion.nonce,
        "body_sha256": assertion.body_sha256,
    }


def encode(secret: bytes, assertion: PrincipalAssertion) -> tuple[str, str]:
    """Return ``(token_b64, signature_hex)`` for the ``X-Aegis-Principal``/``-Signature`` headers."""
    payload = canonical_json(_assertion_payload(assertion))
    token = base64.urlsafe_b64encode(payload).decode("ascii")
    signature = sign(secret, payload)
    return token, signature


def decode_and_verify(
    secret: bytes,
    token: str,
    signature: str,
    *,
    operation: str,
    body: bytes,
    now: datetime,
    claim_nonce: object,
) -> PrincipalAssertion:
    """Decode and fully verify a principal assertion. Raises ``AuthError`` on any violation.

    ``claim_nonce`` is a callable ``(nonce: str, expires_at_iso: str) -> bool`` (typically
    ``SQLiteStore.claim_nonce``); it returns False if the nonce has already been claimed.
    """
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except (ValueError, UnicodeDecodeError) as error:
        raise AuthError("malformed principal assertion") from error

    if not verify_signature(secret, raw, signature):
        raise AuthError("invalid principal assertion signature")

    try:
        data = json.loads(raw)
    except ValueError as error:
        raise AuthError("malformed principal assertion") from error
    if not isinstance(data, Mapping):
        raise AuthError("malformed principal assertion")

    required = {
        "actor_id", "principal_type", "interface", "operation",
        "issued_at", "expires_at", "nonce", "body_sha256",
    }
    if set(data) != required:
        raise AuthError("malformed principal assertion")

    if str(data["operation"]) != operation:
        raise AuthError("principal assertion operation mismatch")

    issued_at = datetime.fromisoformat(str(data["issued_at"]))
    expires_at = datetime.fromisoformat(str(data["expires_at"]))
    if issued_at.tzinfo is None or expires_at.tzinfo is None:
        raise AuthError("principal assertion timestamps must be timezone-aware")
    if now < issued_at or now > expires_at:
        raise AuthError("principal assertion is not currently valid")

    expected_digest = hashlib.sha256(body).hexdigest()
    if str(data["body_sha256"]) != expected_digest:
        raise AuthError("principal assertion body digest mismatch")

    nonce = str(data["nonce"])
    if not claim_nonce(nonce, expires_at.isoformat()):  # type: ignore[operator]
        raise AuthError("principal assertion nonce replayed")

    return PrincipalAssertion(
        actor_id=str(data["actor_id"]),
        principal_type=str(data["principal_type"]),
        interface=str(data["interface"]),
        operation=operation,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
        body_sha256=expected_digest,
    )
