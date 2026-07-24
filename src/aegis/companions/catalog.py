"""Deterministic, authority-removing catalog compiler.

Pure: no filesystem, subprocess, clock, environment, or network access. It combines a
validated ``SubagentsCatalog`` with reviewed ``RoleMappings`` into a ``CompiledCatalog``
whose canonical bytes and SHA-256 are stable across runs and input ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from aegis.companions.subagents import (
    CompiledCatalog,
    RoleMappings,
    SubagentsCatalog,
)


@dataclass(frozen=True)
class CompilationResult:
    catalog: CompiledCatalog
    canonical_bytes: bytes
    sha256: str


def _canonical_bytes(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def compile_catalog(
    source: SubagentsCatalog, mappings: RoleMappings
) -> CompilationResult:
    if {role.id for role in source.roles} != set(mappings.roles):
        raise ValueError("every imported role requires exactly one reviewed mapping")
    compiled = CompiledCatalog.from_reviewed(source, mappings)
    canonical = _canonical_bytes(compiled.model_dump(mode="json"))
    return CompilationResult(compiled, canonical, sha256(canonical).hexdigest())


def build_provenance(
    source: SubagentsCatalog, result: CompilationResult
) -> dict[str, object]:
    """A provenance manifest: source identity, catalog digest, and per-skill record."""
    skills: dict[str, dict[str, str]] = {}
    for role in result.catalog.roles:
        for skill in role.skills:
            skills[skill.id] = {
                "source": skill.source,
                "version": skill.version,
                "sha256": skill.sha256,
                "license": skill.license,
            }
    return {
        "schema_version": 1,
        "source_commit": source.source_commit,
        "source_package_version": source.package_version,
        "source_catalog_schema_version": source.catalog_schema_version,
        "catalog_sha256": result.sha256,
        "skills": dict(sorted(skills.items())),
    }
