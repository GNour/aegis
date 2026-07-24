"""Typed local control-plane client.

This is the only dependency the operator TUI and the Hermes plugin have on Aegis:
one typed method per FR-001 operation, each carrying a signed principal assertion and
(for mutations) an idempotency key. No method accepts a command or argument string, so
neither interface can smuggle arbitrary execution through the client. Errors preserve
the server's stable error code and request id.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from aegis.api.auth import PrincipalAssertion, encode
from aegis.domain.ids import new_uuid7

_DEFAULT_TIMEOUT_S = 10.0


class AegisClientError(RuntimeError):
    def __init__(self, code: str, message: str, request_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


class Signer(Protocol):
    def sign(self, operation: str, body: bytes) -> tuple[str, str]: ...


class HmacSigner:
    def __init__(
        self,
        *,
        secret: bytes,
        actor_id: str,
        principal_type: str = "operator",
        interface: str = "tui",
        ttl_seconds: int = 60,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._secret = secret
        self._actor_id = actor_id
        self._principal_type = principal_type
        self._interface = interface
        self._ttl = ttl_seconds
        self._now = now

    def derive(self, actor_id: str, interface: str) -> "HmacSigner":
        """Return a signer for a different actor/interface sharing the same secret."""
        return HmacSigner(
            secret=self._secret,
            actor_id=actor_id,
            principal_type=self._principal_type,
            interface=interface,
            ttl_seconds=self._ttl,
            now=self._now,
        )

    def sign(self, operation: str, body: bytes) -> tuple[str, str]:
        issued = self._now()
        assertion = PrincipalAssertion(
            actor_id=self._actor_id,
            principal_type=self._principal_type,
            interface=self._interface,
            operation=operation,
            issued_at=issued,
            expires_at=issued + timedelta(seconds=self._ttl),
            nonce=new_uuid7(),
            body_sha256=hashlib.sha256(body).hexdigest(),
        )
        return encode(self._secret, assertion)


def _canonical(body: dict[str, Any] | None) -> bytes:
    if body is None:
        return b""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AegisClient:
    def __init__(
        self,
        *,
        signer: Signer,
        socket_path: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.signer = signer
        if client is not None:
            self.http = client
        elif socket_path is not None:
            self.http = httpx.Client(
                transport=httpx.HTTPTransport(uds=socket_path),
                base_url="http://aegis",
                timeout=timeout,
            )
        else:
            raise ValueError("AegisClient requires either socket_path or client")

    def for_actor(self, actor_id: str, interface: str) -> "AegisClient":
        """Return a client that signs as ``actor_id`` over ``interface``.

        The Hermes plugin uses this to bind each Telegram-mapped operator to their own
        signed assertions while sharing one transport. Falls back to ``self`` when the
        signer cannot be re-scoped.
        """
        derive = getattr(self.signer, "derive", None)
        if not callable(derive):
            return self
        return AegisClient(signer=derive(actor_id, interface), client=self.http)

    def request(
        self,
        method: str,
        path: str,
        operation: str,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        raw = _canonical(body)
        token, signature = self.signer.sign(operation, raw)
        headers = {"X-Aegis-Principal": token, "X-Aegis-Signature": signature}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self.http.request(
                method, path, content=raw if body is not None else None, headers=headers
            )
        except httpx.TimeoutException as error:
            raise AegisClientError("timeout", str(error)) from None
        except httpx.HTTPError as error:
            raise AegisClientError("transport_error", str(error)) from None

        try:
            payload = response.json()
        except ValueError as error:
            raise AegisClientError("invalid_response", "response was not JSON") from error
        if not isinstance(payload, dict):
            raise AegisClientError("invalid_response", "response envelope must be an object")

        request_id = str(payload.get("meta", {}).get("request_id", ""))
        if response.is_error:
            error_body = payload.get("error", {})
            raise AegisClientError(
                str(error_body.get("code", "unknown")),
                str(error_body.get("message", "")),
                request_id,
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AegisClientError("invalid_response", "response data must be an object", request_id)
        return data

    # ── the nine FR-001 operations ───────────────────────────────────────────
    def list_flows(self) -> dict[str, Any]:
        return self.request("GET", "/v1/flows", "flows.read")

    def create_task(
        self,
        *,
        project_id: str,
        request: str,
        flow_id: str = "auto",
        risk: str = "low",
        acceptance_criteria: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/tasks",
            "task.create",
            {
                "project_id": project_id,
                "request": request,
                "flow_id": flow_id,
                "risk": risk,
                "acceptance_criteria": list(acceptance_criteria),
            },
            idempotency_key=idempotency_key,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/tasks/{task_id}", "task.read")

    def approve_action(
        self,
        approval_id: str,
        *,
        action_payload: dict[str, Any],
        comment: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/approvals/{approval_id}:approve",
            "approval.approve",
            {"action_payload": action_payload, "comment": comment},
            idempotency_key=idempotency_key,
        )

    def reject_action(
        self, approval_id: str, *, reason: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/approvals/{approval_id}:reject",
            "approval.reject",
            {"reason": reason},
            idempotency_key=idempotency_key,
        )

    def cancel_task(
        self,
        task_id: str,
        *,
        reason: str,
        cleanup_mode: str = "graceful",
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/tasks/{task_id}:cancel",
            "task.cancel",
            {"reason": reason, "cleanup_mode": cleanup_mode},
            idempotency_key=idempotency_key,
        )

    def resume_task(
        self,
        task_id: str,
        *,
        expected_state: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/tasks/{task_id}:resume",
            "task.resume",
            {
                "expected_state": expected_state,
                "expected_version": expected_version,
                "reason": reason,
            },
            idempotency_key=idempotency_key,
        )

    def create_note(
        self,
        *,
        markdown_text: str,
        project_id: str | None = None,
        task_id: str | None = None,
        source_metadata: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/notes",
            "note.create",
            {
                "project_id": project_id,
                "task_id": task_id,
                "markdown_text": markdown_text,
                "source_metadata": source_metadata or {},
            },
            idempotency_key=idempotency_key,
        )

    def create_reminder(
        self, *, message: str, schedule: str, timezone: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/reminders",
            "reminder.create",
            {"message": message, "schedule": schedule, "timezone": timezone},
            idempotency_key=idempotency_key,
        )
