"""A deterministic fake Herdr Unix-socket server for contract tests.

The Herdr binary is not installed in this environment (see docs/rfcs/0002-herdr.md).
The adapter is therefore validated against this fake, which speaks the same
newline-delimited JSON protocol over a real Unix domain socket. A live probe
against a real instance is gated behind the ``HERDR_SOCKET`` environment variable.
"""

import json
import socket
import threading
from pathlib import Path

import pytest


class FakeHerdr:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self.protocol_version = "1"
        self.requests: list[dict] = []
        self.sessions: dict[str, str] = {}
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(socket_path))
        self._server.listen(8)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _result(self, method: str, params: dict) -> dict:
        if method == "schema":
            return {
                "protocol_version": self.protocol_version,
                "methods": {"agent.start": {}, "agent.inspect": {}, "agent.resume": {}},
            }
        if method == "agent.start":
            return {
                "session_id": "pane-17",
                "native_session_id": "ses_123",
                "state": "running",
            }
        if method == "agent.inspect":
            return {
                "session_id": params["session_id"],
                "native_session_id": "ses_123",
                "state": "waiting_input",
            }
        if method == "agent.resume":
            return {
                "session_id": params["session_id"],
                "native_session_id": "ses_123",
                "state": "running",
            }
        if method == "agent.interrupt":
            return {"session_id": params["session_id"], "state": "interrupted"}
        if method == "agent.remove":
            return {"session_id": params["session_id"], "removed": True}
        raise KeyError(method)

    def _handle(self, conn: socket.socket) -> None:
        buffer = b""
        while not self._stop.is_set():
            chunk = conn.recv(65536)
            if not chunk:
                return
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line.decode("utf-8"))
                self.requests.append(message)
                try:
                    result = self._result(message["method"], message.get("params", {}))
                    response = {"ok": True, "result": result}
                except KeyError as error:
                    response = {"ok": False, "error": {"code": "unknown_method", "message": str(error)}}
                conn.sendall(json.dumps(response).encode("utf-8") + b"\n")

    def _serve(self) -> None:
        self._server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except OSError:
                continue
            with conn:
                try:
                    self._handle(conn)
                except (OSError, ValueError):
                    return

    def close(self) -> None:
        self._stop.set()
        self._server.close()
        self._thread.join(timeout=2)


@pytest.fixture
def fake_herdr(tmp_path):
    server = FakeHerdr(tmp_path / "herdr.sock")
    try:
        yield server
    finally:
        server.close()
