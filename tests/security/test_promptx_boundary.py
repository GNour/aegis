import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.companions.promptx import (
    BrokerLease,
    ProcessResult,
    PromptXAdapter,
    PromptXAuditRecord,
    PromptXProtocolError,
    PromptXRequest,
)

FIXTURES = Path(__file__).resolve().parents[1] / "companions" / "fixtures"
CANARY = "CANARY-TOKEN-SECRET"
VERSION = b'{"package_version":"1.0.0-aegis.0","protocol_version":"1"}'


def request(mode: str = "deterministic-only") -> PromptXRequest:
    return PromptXRequest.model_validate(
        {
            "mode": mode,
            "task_id": "task-1",
            "task_class": "debug",
            "metadata": {},
            "facts": [{"name": "cmd", "value": "uv run pytest", "source_digest": "a" * 64}],
        }
    )


def make(tmp_path: Path, run_process, sink: list) -> PromptXAdapter:
    exe = tmp_path / "promptx"
    exe.write_bytes(b"stub")
    return PromptXAdapter(
        executable=exe,
        expected_sha256=sha256(b"stub").hexdigest(),
        expected_package_version="1.0.0-aegis.0",
        expected_protocol_version="1",
        run_process=run_process,
        audit=sink.append,
        digest_file=lambda _p: sha256(b"stub").hexdigest(),
    )


def test_broker_url_must_be_loopback() -> None:
    for bad in ("http://evil.example/v1", "https://127.0.0.1:4319/v1", "http://10.0.0.1:4319/v1"):
        with pytest.raises(ValidationError):
            BrokerLease(reference="r", token="t", url=bad)


def test_child_env_excludes_provider_and_unrelated_vars(tmp_path: Path) -> None:
    seen: list[dict] = []
    body = (FIXTURES / "promptx-degraded.json").read_bytes()

    def run_process(argv, *, input, env, timeout):
        seen.append(env)
        return ProcessResult(0, VERSION if input == b"" else body, b"")

    sink: list = []
    make(tmp_path, run_process, sink).enrich(
        request("brokered-refinement"),
        broker=BrokerLease(reference="broker:t:s", token=CANARY, url="http://127.0.0.1:4319/v1"),
    )
    enrich_env = seen[-1]
    assert set(enrich_env) <= {"LANG", "LC_ALL", "PROMPTX_BROKER_URL", "PROMPTX_BROKER_TOKEN"}
    assert "OPENAI_API_KEY" not in enrich_env
    assert "PATH" not in enrich_env


def test_broker_token_never_enters_audit_or_result(tmp_path: Path) -> None:
    body = (FIXTURES / "promptx-degraded.json").read_bytes()

    def run_process(argv, *, input, env, timeout):
        return ProcessResult(0, VERSION if input == b"" else body, b"")

    sink: list[PromptXAuditRecord] = []
    result = make(tmp_path, run_process, sink).enrich(
        request("brokered-refinement"),
        broker=BrokerLease(reference="broker:t:s", token=CANARY, url="http://127.0.0.1:4319/v1"),
    )
    assert CANARY not in result.model_dump_json()
    assert CANARY not in sink[0].model_dump_json()


def test_timeout_is_audited_once_and_body_free(tmp_path: Path) -> None:
    def run_process(argv, *, input, env, timeout):
        if input == b"":
            return ProcessResult(0, VERSION, b"")
        raise subprocess.TimeoutExpired(cmd="promptx", timeout=timeout)

    sink: list = []
    with pytest.raises(PromptXProtocolError) as excinfo:
        make(tmp_path, run_process, sink).enrich(request())
    assert "secret" not in str(excinfo.value).lower()
    assert len(sink) == 1
    assert sink[0].output_digest is None


def test_protocol_rejection_is_audited_once(tmp_path: Path) -> None:
    rejected = b'{"protocol_version":"1","outcome_code":"AEGIS_REJECTED_INVALID_REQUEST","diagnostics":{"duration_ms":0,"token_usage":{"input_tokens":0,"output_tokens":0}}}'

    def run_process(argv, *, input, env, timeout):
        return ProcessResult(0, VERSION if input == b"" else rejected, b"")

    sink: list = []
    with pytest.raises(PromptXProtocolError, match="rejected"):
        make(tmp_path, run_process, sink).enrich(request())
    assert len(sink) == 1


def test_stderr_body_never_enters_exception(tmp_path: Path) -> None:
    def run_process(argv, *, input, env, timeout):
        if input == b"":
            return ProcessResult(0, VERSION, b"")
        return ProcessResult(0, b"not json at all", b"SENSITIVE-STDERR-BODY")

    sink: list = []
    with pytest.raises(PromptXProtocolError) as excinfo:
        make(tmp_path, run_process, sink).enrich(request())
    assert "SENSITIVE-STDERR-BODY" not in str(excinfo.value)
    assert len(sink) == 1
