"""Contract tests for the typed local control-plane client."""

import json

import httpx
import pytest

from aegis.client import AegisClient, AegisClientError, HmacSigner

SECRET = b"test-secret-do-not-use-in-production"


class FakeApi:
    def __init__(self) -> None:
        self.last_request: httpx.Request | None = None
        self._status = 200
        self._payload: dict = {"data": {"ok": True}, "meta": {"request_id": "r0"}}
        self.transport = httpx.MockTransport(self._handle)

    def respond(self, status: int, payload: dict) -> None:
        self._status = status
        self._payload = payload

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(self._status, json=self._payload)


@pytest.fixture
def fake_api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def client(fake_api: FakeApi) -> AegisClient:
    http = httpx.Client(transport=fake_api.transport, base_url="http://aegis")
    signer = HmacSigner(secret=SECRET, actor_id="018f8bd9-19d6-7902-9018-593c0a97ea8a")
    return AegisClient(signer=signer, client=http)


def test_create_task_sends_idempotency_and_assertion(fake_api, client) -> None:
    fake_api.respond(201, {"data": {"task_id": "task-001"}, "meta": {"request_id": "r1"}})
    client.create_task(
        project_id="demo", request="fix login", flow_id="auto", idempotency_key="k1"
    )
    request = fake_api.last_request
    assert request.headers["Idempotency-Key"] == "k1"
    assert request.headers["X-Aegis-Principal"]
    assert request.headers["X-Aegis-Signature"]
    assert json.loads(request.content)["flow_id"] == "auto"


def test_signed_body_digest_matches_transmitted_bytes(fake_api, client) -> None:
    import hashlib

    client.create_task(project_id="demo", request="x", idempotency_key="k2")
    body = fake_api.last_request.content
    import base64

    token = fake_api.last_request.headers["X-Aegis-Principal"]
    assertion = json.loads(base64.urlsafe_b64decode(token))
    assert assertion["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert assertion["operation"] == "task.create"


def test_error_code_is_preserved(fake_api, client) -> None:
    fake_api.respond(
        409,
        {"error": {"code": "state_conflict", "message": "changed"}, "meta": {"request_id": "r1"}},
    )
    with pytest.raises(AegisClientError) as error:
        client.resume_task(
            "t1", expected_state="paused", expected_version=2, reason="retry", idempotency_key="k3"
        )
    assert error.value.code == "state_conflict"
    assert error.value.request_id == "r1"


def test_list_flows_uses_get_and_flows_read_operation(fake_api, client) -> None:
    fake_api.respond(200, {"data": {"flows": []}, "meta": {"request_id": "r1"}})
    client.list_flows()
    assert fake_api.last_request.method == "GET"
    assert fake_api.last_request.url.path == "/v1/flows"


def test_all_nine_operations_are_present(client) -> None:
    for name in (
        "list_flows",
        "create_task",
        "get_task",
        "approve_action",
        "reject_action",
        "cancel_task",
        "resume_task",
        "create_note",
        "create_reminder",
    ):
        assert callable(getattr(client, name))


def test_timeout_is_mapped_to_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://aegis")
    signer = HmacSigner(secret=SECRET, actor_id="018f8bd9-19d6-7902-9018-593c0a97ea8a")
    client = AegisClient(signer=signer, client=http)
    with pytest.raises(AegisClientError) as error:
        client.list_flows()
    assert error.value.code == "timeout"


def test_non_json_response_is_mapped_to_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>nope</html>")

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://aegis")
    signer = HmacSigner(secret=SECRET, actor_id="018f8bd9-19d6-7902-9018-593c0a97ea8a")
    client = AegisClient(signer=signer, client=http)
    with pytest.raises(AegisClientError) as error:
        client.list_flows()
    assert error.value.code == "invalid_response"
