"""Bounded companion readiness evaluation.

Pure decision logic: given the admitted lock and freshly computed artifact digests,
decide whether the companions are safe to dispatch against. The result carries only
stable codes and safe version/digest names — never paths, subprocess bodies, environment
values, prompts, facts, or credentials.
"""

from __future__ import annotations

from pathlib import Path

from aegis.companions.lock import CompanionLock


def load_lock(root: Path) -> CompanionLock:
    return CompanionLock.model_validate_json(
        (root / "config" / "companions.lock.json").read_text(encoding="utf-8")
    )


def evaluate(
    lock: CompanionLock,
    *,
    promptx_artifact_digest: str,
    subagents_artifact_digest: str,
    sources_clean: bool,
) -> dict[str, object]:
    if not sources_clean:
        return {"ready": False, "code": "companion_source_dirty"}
    if promptx_artifact_digest != lock.promptx.artifact_sha256:
        return {"ready": False, "code": "promptx_artifact_mismatch"}
    if subagents_artifact_digest != lock.subagents.artifact_sha256:
        return {"ready": False, "code": "subagents_artifact_mismatch"}
    return {
        "ready": True,
        "code": "ready",
        "promptx_package_version": lock.promptx.package_version,
        "promptx_protocol_version": lock.promptx.contract_version,
        "subagents_package_version": lock.subagents.package_version,
        "subagents_catalog_schema_version": lock.subagents.contract_version,
    }
