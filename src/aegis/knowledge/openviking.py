"""Source-linked OpenViking memory adapter.

OpenViking is adopted behind a narrow adapter (docs/rfcs/0003-openviking.md). It is
not running in this environment, so the adapter is validated against an injectable
transport. Recall returns only memories that belong to the requesting project and
carry both a source commit and a source URI, so every fact is traceable to canonical
Git. The production transport uses an authenticated loopback client with bounded
timeouts and a readiness check, and redacts the API key from every error.
"""

from pathlib import Path
from typing import Any, Protocol

import httpx

_DEFAULT_TIMEOUT_S = 5.0
_MAX_LIMIT = 20


class OpenVikingError(RuntimeError):
    """An OpenViking request failed (transport error, timeout, or bad status)."""


def redact(text: str, secret: str) -> str:
    """Replace ``secret`` with ``***`` so it never reaches a log or exception."""
    return text.replace(secret, "***") if secret else text


class Transport(Protocol):
    def post(self, path: str, json: dict[str, Any]) -> Any: ...
    def ready(self) -> bool: ...


class MemoryTransport:
    """In-memory transport for tests; records calls and can inject one failure."""

    def __init__(self) -> None:
        self.responses: list[dict[str, Any]] = []
        self.fail_next = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._ready = True

    def ready(self) -> bool:
        return self._ready

    def post(self, path: str, json: dict[str, Any]) -> Any:
        self.calls.append((path, json))
        if self.fail_next:
            self.fail_next = False
            raise OpenVikingError("transport failure")
        if path.endswith("/search"):
            return self.responses
        if path.endswith("/resources"):
            return {"receipt_id": "rcpt-123"}
        raise OpenVikingError(f"unknown path: {path}")


class HttpTransport:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "http://127.0.0.1:8790",
        client: httpx.Client | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @classmethod
    def from_key_file(
        cls, *, base_url: str, key_path: Path, timeout: float = _DEFAULT_TIMEOUT_S
    ) -> "HttpTransport":
        api_key = Path(key_path).read_text(encoding="utf-8").strip()
        return cls(api_key=api_key, base_url=base_url, timeout=timeout)

    def ready(self) -> bool:
        try:
            response = self._client.get("/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def post(self, path: str, json: dict[str, Any]) -> Any:
        try:
            response = self._client.post(path, json=json)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise OpenVikingError("openviking request timed out") from None
        except httpx.HTTPError as error:
            raise OpenVikingError(redact(str(error), self._api_key)) from None
        return response.json()


class OpenVikingAdapter:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def recall(self, project_id: str, query: str, limit: int) -> list[dict[str, object]]:
        raw = self.transport.post(
            "/api/v1/search", {"query": query, "limit": min(limit, _MAX_LIMIT)}
        )
        return [item for item in raw if self._is_source_linked(item, project_id)]

    @staticmethod
    def _is_source_linked(item: dict[str, Any], project_id: str) -> bool:
        metadata = item.get("metadata", {})
        return bool(
            metadata.get("project_id") == project_id
            and metadata.get("source_commit")
            and metadata.get("source_uri")
        )

    def ingest_commit(
        self, project_id: str, source_uri: str, commit: str, markdown: str
    ) -> str:
        result = self.transport.post(
            "/api/v1/resources",
            {
                "project_id": project_id,
                "source_uri": source_uri,
                "source_commit": commit,
                "content": markdown,
            },
        )
        return str(result["receipt_id"])
