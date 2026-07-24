"""Contract tests for the source-linked OpenViking memory adapter."""

import httpx
import pytest

from aegis.knowledge.openviking import (
    HttpTransport,
    MemoryTransport,
    OpenVikingAdapter,
    OpenVikingError,
    redact,
)


@pytest.fixture
def openviking() -> OpenVikingAdapter:
    return OpenVikingAdapter(MemoryTransport())


def test_memory_without_source_commit_is_excluded(openviking) -> None:
    openviking.transport.responses = [
        {"uri": "viking://m/1", "text": "fact", "metadata": {"project_id": "a"}}
    ]
    assert openviking.recall(project_id="a", query="fact", limit=5) == []


def test_foreign_project_memory_is_excluded(openviking) -> None:
    openviking.transport.responses = [
        {
            "uri": "viking://m/2",
            "text": "fact",
            "metadata": {"project_id": "b", "source_commit": "abc", "source_uri": "git://brain/a.md"},
        }
    ]
    assert openviking.recall(project_id="a", query="fact", limit=5) == []


def test_source_linked_project_memory_is_returned(openviking) -> None:
    item = {
        "uri": "viking://m/3",
        "text": "fact",
        "metadata": {"project_id": "a", "source_commit": "abc", "source_uri": "git://brain/a.md"},
    }
    openviking.transport.responses = [item]
    assert openviking.recall(project_id="a", query="fact", limit=5) == [item]


def test_ingest_returns_receipt(openviking) -> None:
    receipt = openviking.ingest_commit(
        project_id="a", source_uri="git://brain/a.md", commit="abc", markdown="# note"
    )
    assert receipt == "rcpt-123"


def test_transport_failure_raises(openviking) -> None:
    openviking.transport.fail_next = True
    with pytest.raises(OpenVikingError):
        openviking.recall(project_id="a", query="fact", limit=5)


def test_recall_limit_is_capped_in_request(openviking) -> None:
    openviking.recall(project_id="a", query="fact", limit=100)
    path, body = openviking.transport.calls[-1]
    assert body["limit"] <= 20


# ── production HttpTransport (via httpx.MockTransport) ────────────────────────
def test_http_transport_readiness_reflects_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.url.path == "/health" else 404)

    client = httpx.Client(base_url="http://loopback", transport=httpx.MockTransport(handler))
    transport = HttpTransport(api_key="secret-key", client=client)
    assert transport.ready() is True


def test_http_transport_maps_timeout_to_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    client = httpx.Client(base_url="http://loopback", transport=httpx.MockTransport(handler))
    transport = HttpTransport(api_key="secret-key", client=client)
    with pytest.raises(OpenVikingError, match="timed out"):
        transport.post("/api/v1/search", {"query": "x", "limit": 5})


def test_http_transport_redacts_api_key_from_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom secret-key leaked")

    client = httpx.Client(base_url="http://loopback", transport=httpx.MockTransport(handler))
    transport = HttpTransport(api_key="secret-key", client=client)
    with pytest.raises(OpenVikingError) as excinfo:
        transport.post("/api/v1/resources", {"content": "x"})
    assert "secret-key" not in str(excinfo.value)


def test_redact_helper() -> None:
    assert redact("token=secret-key here", "secret-key") == "token=*** here"
    assert redact("no secret", "") == "no secret"
