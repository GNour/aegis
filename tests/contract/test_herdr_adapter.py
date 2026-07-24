"""Contract tests for the narrow Herdr socket adapter."""

import os

import pytest

from aegis.execution.herdr import HerdrClient, HerdrProtocolError


def test_start_returns_both_session_identifiers(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    session = client.start(agent="opencode", cwd="/tasks/t1", argv=["opencode", "run"])
    assert session.herdr_id == "pane-17"
    assert session.native_id == "ses_123"
    assert session.state == "running"


def test_unknown_protocol_is_rejected(fake_herdr) -> None:
    fake_herdr.protocol_version = "99"
    client = HerdrClient(fake_herdr.socket_path)
    assert client.compatible() is False


def test_supported_protocol_is_accepted(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    assert client.compatible() is True


def test_inspect_and_resume_correlate_native_session(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    inspected = client.inspect("pane-17")
    assert inspected.native_id == "ses_123"
    resumed = client.resume("pane-17")
    assert resumed.state == "running"


def test_interrupt_and_remove(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    assert client.interrupt("pane-17").state == "interrupted"
    assert client.remove("pane-17") is True


def test_unknown_method_raises_protocol_error(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path)
    with pytest.raises(HerdrProtocolError):
        client.request("agent.bogus", {})


def test_oversized_response_is_rejected(fake_herdr) -> None:
    client = HerdrClient(fake_herdr.socket_path, max_message_bytes=8)
    with pytest.raises(HerdrProtocolError, match="response exceeds"):
        client.schema()


@pytest.mark.skipif(
    "HERDR_SOCKET" not in os.environ, reason="live Herdr socket not configured"
)
def test_live_herdr_is_compatible() -> None:
    client = HerdrClient(os.environ["HERDR_SOCKET"])
    assert client.compatible() is True
