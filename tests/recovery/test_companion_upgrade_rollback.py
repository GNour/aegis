"""Coordinated companion upgrade/rollback keeps one compatible, verified set."""

from aegis.companions.lock import CompanionLock
from aegis.companions.readiness import evaluate


def _lock(promptx_digest: str, subagents_digest: str, version: str) -> CompanionLock:
    return CompanionLock.model_validate(
        {
            "schema_version": 1,
            "promptx": {
                "path": "packages/promptx",
                "source_url": "https://github.com/GNour/promptx.git",
                "source_commit": "a" * 40,
                "package_version": version,
                "contract_version": "1",
                "artifact_sha256": promptx_digest,
                "sbom_sha256": "3" * 64,
                "license_spdx": "MIT",
            },
            "subagents": {
                "path": "packages/subagents",
                "source_url": "https://github.com/GNour/subagents.git",
                "source_commit": "b" * 40,
                "package_version": version,
                "contract_version": "1",
                "artifact_sha256": subagents_digest,
                "sbom_sha256": "4" * 64,
                "license_spdx": "MIT",
            },
        }
    )


PREVIOUS = _lock("1" * 64, "2" * 64, "1.0.0-aegis.0")
CURRENT = _lock("5" * 64, "6" * 64, "1.1.0-aegis.0")


def test_rollback_restores_one_compatible_companion_set() -> None:
    verdict = evaluate(
        PREVIOUS,
        promptx_artifact_digest="1" * 64,
        subagents_artifact_digest="2" * 64,
        sources_clean=True,
    )
    assert verdict["ready"] is True
    assert verdict["promptx_package_version"] == "1.0.0-aegis.0"


def test_mixing_previous_promptx_with_current_lock_fails_before_dispatch() -> None:
    verdict = evaluate(
        CURRENT,
        promptx_artifact_digest="1" * 64,  # previous promptx artifact
        subagents_artifact_digest="6" * 64,  # current subagents
        sources_clean=True,
    )
    assert verdict["ready"] is False
    assert verdict["code"] == "promptx_artifact_mismatch"
