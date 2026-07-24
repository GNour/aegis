from pathlib import Path

import pytest
import yaml

from aegis.companions.catalog import compile_catalog
from aegis.companions.subagents import RoleMappings, SubagentsCatalog

ROOT = Path(__file__).resolve().parents[2].parent
CATALOG_SRC = ROOT / "packages" / "subagents" / "dist" / "catalog.json"
MAPPINGS_SRC = ROOT / "config" / "companions" / "role-mappings.yaml"


@pytest.fixture
def real_catalog() -> SubagentsCatalog:
    return SubagentsCatalog.model_validate_json(CATALOG_SRC.read_text(encoding="utf-8"))


@pytest.fixture
def real_mappings() -> RoleMappings:
    return RoleMappings.model_validate(
        yaml.safe_load(MAPPINGS_SRC.read_text(encoding="utf-8"))
    )


def _skill(sid: str) -> dict:
    return {
        "id": sid,
        "source": f"skills.sh:{sid}",
        "version": "advisory-000000000001",
        "sha256": "a" * 64,
        "license": "advisory-unverified",
    }


def _catalog(role_skills: list[str]) -> SubagentsCatalog:
    return SubagentsCatalog.model_validate(
        {
            "package_version": "1.0.0",
            "catalog_schema_version": "1",
            "source_commit": "a" * 40,
            "departments": [{"id": "engineering", "name": "Engineering"}],
            "roles": [
                {
                    "id": "solo",
                    "department_id": "engineering",
                    "name": "solo",
                    "title": "Solo",
                    "description": "d",
                    "expertise": ["x"],
                    "invocation": "1. do",
                    "standards": ["s"],
                    "model_hint": "sonnet",
                    "advisory_tools": ["Read", "Bash"],
                    "skills": [_skill(s) for s in role_skills],
                    "handoffs": [],
                }
            ],
        }
    )


def _mappings(skills: list[str], tools: list[str]) -> RoleMappings:
    return RoleMappings.model_validate(
        {
            "schema_version": 1,
            "roles": {
                "solo": {
                    "model_alias": "implementation",
                    "capability_profile": "worktree-write",
                    "skills": skills,
                    "tools": tools,
                }
            },
        }
    )


def test_compilation_is_deterministic(
    real_catalog: SubagentsCatalog, real_mappings: RoleMappings
) -> None:
    first = compile_catalog(real_catalog, real_mappings)
    second = compile_catalog(
        SubagentsCatalog.model_validate_json(real_catalog.model_dump_json()),
        real_mappings,
    )
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256


def test_unmapped_role_fails_closed() -> None:
    catalog = _catalog(["owner/a"])
    empty = RoleMappings.model_validate({"schema_version": 1, "roles": {}})
    with pytest.raises(ValueError, match="reviewed mapping"):
        compile_catalog(catalog, empty)


def test_mapped_skill_absent_from_provenance_fails() -> None:
    catalog = _catalog(["owner/a"])
    mappings = _mappings(["owner/ghost"], ["qmd_get"])
    with pytest.raises(ValueError, match="absent from provenance"):
        compile_catalog(catalog, mappings)


def test_tool_outside_registry_fails() -> None:
    catalog = _catalog(["owner/a"])
    mappings = _mappings(["owner/a"], ["Bash"])
    with pytest.raises(ValueError, match="registry"):
        compile_catalog(catalog, mappings)
