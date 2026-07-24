from hashlib import sha256
from pathlib import Path

import pytest

from aegis.companions.promptx import (
    BrokerLease,
    ProcessResult,
    PromptXAdapter,
    PromptXProtocolError,
    PromptXRequest,
)

FIXTURES = Path(__file__).resolve().parents[2] / "companions" / "fixtures"
DIGEST = "b" * 64


def request(mode: str = "deterministic-only") -> PromptXRequest:
    return PromptXRequest.model_validate(
        {
            "mode": mode,
            "task_id": "task-1",
            "task_class": "debug",
            "metadata": {"service": "payments"},
            "facts": [
                {"name": "test_command", "value": "uv run pytest", "source_digest": "a" * 64}
            ],
        }
    )


def adapter(tmp_path: Path, fixture: str, *, audit_sink: list | None = None) -> PromptXAdapter:
    exe = tmp_path / "promptx"
    exe.write_bytes(b"stub")
    body = (FIXTURES / fixture).read_bytes()
    sink = audit_sink if audit_sink is not None else []
    return PromptXAdapter(
        executable=exe,
        expected_sha256=sha256(b"stub").hexdigest(),
        expected_package_version="1.0.0-aegis.0",
        expected_protocol_version="1",
        run_process=lambda *a, **k: _dispatch(k.get("input", b""), body),
        audit=sink.append,
        digest_file=lambda _p: sha256(b"stub").hexdigest(),
    )


def _dispatch(stdin: bytes, body: bytes) -> ProcessResult:
    # readiness probe sends empty stdin; return a version block for that call.
    if stdin == b"":
        return ProcessResult(
            0, b'{"package_version":"1.0.0-aegis.0","protocol_version":"1"}', b""
        )
    return ProcessResult(0, body, b"")


def test_deterministic_success_returns_context(tmp_path: Path) -> None:
    result = adapter(tmp_path, "promptx-success.json").enrich(request())
    assert result.degraded is False
    assert result.additional_context
    assert result.outcome_code == "AEGIS_SUCCESS_DETERMINISTIC"


def test_broker_unavailable_degrades_but_keeps_deterministic_context(tmp_path: Path) -> None:
    result = adapter(tmp_path, "promptx-degraded.json").enrich(
        request("brokered-refinement"),
        broker=BrokerLease(reference="broker:task:stage", token="opaque", url="http://127.0.0.1:4319/v1"),
    )
    assert result.degraded is True
    assert result.additional_context  # deterministic result still available


def test_authority_bearing_output_fails_closed(tmp_path: Path) -> None:
    sink: list = []
    ad = adapter(tmp_path, "promptx-unknown-field.json", audit_sink=sink)
    with pytest.raises(PromptXProtocolError, match="invalid PromptX response"):
        ad.enrich(request())
    assert len(sink) == 1  # exactly one audit record on the rejection


def test_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    exe = tmp_path / "promptx"
    exe.write_bytes(b"stub")
    ad = PromptXAdapter(
        executable=exe,
        expected_sha256="c" * 64,  # wrong
        expected_package_version="1.0.0-aegis.0",
        expected_protocol_version="1",
        run_process=lambda *a, **k: ProcessResult(0, b"{}", b""),
        audit=lambda _r: None,
        digest_file=lambda _p: sha256(b"stub").hexdigest(),
    )
    with pytest.raises(PromptXProtocolError, match="digest mismatch"):
        ad.enrich(request())
