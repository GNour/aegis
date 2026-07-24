"""The PromptX child environment is fresh: host secrets never propagate to it."""

from hashlib import sha256
from pathlib import Path

from aegis.companions.promptx import (
    BrokerLease,
    ProcessResult,
    PromptXAdapter,
    PromptXRequest,
)

VERSION = b'{"package_version":"1.0.0-aegis.0","protocol_version":"1"}'
CANARY = "OPENAI_API_KEY_CANARY_VALUE"


def _request() -> PromptXRequest:
    return PromptXRequest.model_validate(
        {
            "mode": "brokered-refinement",
            "task_id": "task-1",
            "task_class": "debug",
            "metadata": {},
            "facts": [{"name": "cmd", "value": "uv run pytest", "source_digest": "a" * 64}],
        }
    )


def test_host_provider_secret_does_not_reach_child(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", CANARY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", CANARY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", CANARY)

    body = (
        b'{"protocol_version":"1","outcome_code":"AEGIS_DEGRADED_BROKER_UNAVAILABLE",'
        b'"result":{"additional_context":"Fact (cmd) \\u2014 uv run pytest"},'
        b'"diagnostics":{"gate":{"verdict":"augment","reason":"aegis-injected-facts"},'
        b'"task_class":"debug","quality":"injected-facts","fact_digests":["' + b"a" * 64 + b'"],'
        b'"provider":{"state":"unavailable"},"duration_ms":1,'
        b'"token_usage":{"input_tokens":1,"output_tokens":1}}}'
    )
    envs: list[dict] = []

    def run_process(argv, *, input, env, timeout):
        envs.append(env)
        return ProcessResult(0, VERSION if input == b"" else body, b"")

    exe = tmp_path / "promptx"
    exe.write_bytes(b"stub")
    adapter = PromptXAdapter(
        executable=exe,
        expected_sha256=sha256(b"stub").hexdigest(),
        expected_package_version="1.0.0-aegis.0",
        expected_protocol_version="1",
        run_process=run_process,
        audit=lambda _r: None,
        digest_file=lambda _p: sha256(b"stub").hexdigest(),
    )
    adapter.enrich(
        _request(),
        broker=BrokerLease(reference="broker:t:s", token="opaque", url="http://127.0.0.1:4319/v1"),
    )
    for env in envs:
        assert CANARY not in env.values()
        assert "OPENAI_API_KEY" not in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "AWS_SECRET_ACCESS_KEY" not in env
