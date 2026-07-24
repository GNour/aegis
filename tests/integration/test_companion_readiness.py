import json
from pathlib import Path

from typer.testing import CliRunner

from aegis.cli import app
from aegis.companions.readiness import evaluate, load_lock

ROOT = Path(__file__).resolve().parents[2]


def test_readiness_rejects_promptx_digest_mismatch() -> None:
    lock = load_lock(ROOT)
    verdict = evaluate(
        lock,
        promptx_artifact_digest="0" * 64,  # wrong
        subagents_artifact_digest=lock.subagents.artifact_sha256,
        sources_clean=True,
    )
    assert verdict["ready"] is False
    assert verdict["code"] == "promptx_artifact_mismatch"


def test_readiness_rejects_dirty_sources() -> None:
    lock = load_lock(ROOT)
    verdict = evaluate(
        lock,
        promptx_artifact_digest=lock.promptx.artifact_sha256,
        subagents_artifact_digest=lock.subagents.artifact_sha256,
        sources_clean=False,
    )
    assert verdict == {"ready": False, "code": "companion_source_dirty"}


def test_ready_when_digests_match() -> None:
    lock = load_lock(ROOT)
    verdict = evaluate(
        lock,
        promptx_artifact_digest=lock.promptx.artifact_sha256,
        subagents_artifact_digest=lock.subagents.artifact_sha256,
        sources_clean=True,
    )
    assert verdict["ready"] is True
    assert verdict["code"] == "ready"
    assert verdict["subagents_catalog_schema_version"] == "1"


def test_cli_verify_emits_safe_json() -> None:
    result = CliRunner().invoke(app, ["companions", "verify"])
    payload = json.loads(result.stdout)
    assert "ready" in payload and "code" in payload
    # never leaks paths/credentials
    assert "/home" not in result.stdout
