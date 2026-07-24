"""Narrow adapter for the Herdr durable-session multiplexer.

Herdr is adopted behind a narrow adapter (docs/rfcs/0002-herdr.md). The binary is
not installed in this environment, so the adapter is validated against a
deterministic fake that speaks the same newline-delimited JSON protocol over a
private Unix socket. Every response is validated with Pydantic, message sizes are
bounded, and unsupported protocol versions are refused before any dispatch.
"""

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

_DEFAULT_MAX_MESSAGE_BYTES = 1 << 20  # 1 MiB
_DEFAULT_TIMEOUT_S = 30.0


class HerdrProtocolError(RuntimeError):
    """The Herdr server returned an error, malformed, or oversized response."""


@dataclass(frozen=True)
class AgentSession:
    herdr_id: str
    native_id: str | None
    state: str


class _StartResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str
    native_session_id: str | None = None
    state: str


class _RemoveResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str
    removed: bool


class HerdrClient:
    SUPPORTED_PROTOCOLS = frozenset({"1"})

    def __init__(
        self,
        socket_path: Path | str,
        *,
        max_message_bytes: int = _DEFAULT_MAX_MESSAGE_BYTES,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.socket_path = Path(socket_path)
        self._max_message_bytes = max_message_bytes
        self._timeout = timeout

    def schema(self) -> dict[str, Any]:
        return self.request("schema", {})

    def compatible(self) -> bool:
        try:
            version = self.schema().get("protocol_version")
        except HerdrProtocolError:
            return False
        return version in self.SUPPORTED_PROTOCOLS

    def _require_compatible(self) -> None:
        if not self.compatible():
            raise HerdrProtocolError("unsupported Herdr protocol version")

    def start(self, *, agent: str, cwd: str, argv: list[str]) -> AgentSession:
        self._require_compatible()
        result = _StartResult.model_validate(
            self.request("agent.start", {"agent": agent, "cwd": cwd, "argv": argv})
        )
        return AgentSession(result.session_id, result.native_session_id, result.state)

    def inspect(self, session_id: str) -> AgentSession:
        result = _StartResult.model_validate(
            self.request("agent.inspect", {"session_id": session_id})
        )
        return AgentSession(result.session_id, result.native_session_id, result.state)

    def resume(self, session_id: str) -> AgentSession:
        self._require_compatible()
        result = _StartResult.model_validate(
            self.request("agent.resume", {"session_id": session_id})
        )
        return AgentSession(result.session_id, result.native_session_id, result.state)

    def interrupt(self, session_id: str) -> AgentSession:
        result = _StartResult.model_validate(
            self.request("agent.interrupt", {"session_id": session_id})
        )
        return AgentSession(result.session_id, result.native_session_id, result.state)

    def remove(self, session_id: str) -> bool:
        result = _RemoveResult.model_validate(
            self.request("agent.remove", {"session_id": session_id})
        )
        return result.removed

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps({"method": method, "params": params}).encode("utf-8")
        raw = self._roundtrip(payload + b"\n")
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HerdrProtocolError("malformed Herdr response") from error
        if not isinstance(envelope, dict) or "ok" not in envelope:
            raise HerdrProtocolError("malformed Herdr envelope")
        if not envelope["ok"]:
            error_body = envelope.get("error", {})
            raise HerdrProtocolError(f"herdr error: {error_body}")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise HerdrProtocolError("herdr result must be an object")
        return result

    def _roundtrip(self, payload: bytes) -> bytes:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(self._timeout)
            conn.connect(str(self.socket_path))
            conn.sendall(payload)
            buffer = b""
            while b"\n" not in buffer:
                chunk = conn.recv(65536)
                if not chunk:
                    raise HerdrProtocolError("connection closed before response")
                buffer += chunk
                if len(buffer) > self._max_message_bytes:
                    raise HerdrProtocolError("response exceeds maximum message size")
            return buffer.split(b"\n", 1)[0]
