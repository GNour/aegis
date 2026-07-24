import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from aegis.companions.subagents import (
    CompiledCatalog,
    RoleMappings,
    SubagentsCatalog,
)

FIXTURES = Path(__file__).resolve().parents[2] / "companions" / "fixtures"
ROLE_MAPPINGS = (
    Path(__file__).resolve().parents[2].parent
    / "config"
    / "companions"
    / "role-mappings.yaml"
)


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_catalog_preserves_advisory_fields_without_granting_authority() -> None:
    catalog = SubagentsCatalog.model_validate(load("subagents-valid.json"))
    assert catalog.catalog_schema_version == "1"
    assert catalog.roles[0].advisory_tools == ("Read", "Grep")


@pytest.mark.parametrize(
    "fixture",
    ["subagents-unknown-field.json", "subagents-duplicate-role.json"],
)
def test_malformed_catalog_fails_closed(fixture: str) -> None:
    with pytest.raises(ValidationError):
        SubagentsCatalog.model_validate(load(fixture))


def test_role_mappings_parse_strictly() -> None:
    data = yaml.safe_load(ROLE_MAPPINGS.read_text(encoding="utf-8"))
    mappings = RoleMappings.model_validate(data)
    assert mappings.schema_version == 1
    assert mappings.roles  # non-empty


def test_reviewed_mappings_cover_every_real_role() -> None:
    catalog = SubagentsCatalog.model_validate_json(
        (ROLE_MAPPINGS.parent.parent.parent / "packages" / "subagents" / "dist" / "catalog.json")
        .read_text(encoding="utf-8")
    )
    mappings = RoleMappings.model_validate(
        yaml.safe_load(ROLE_MAPPINGS.read_text(encoding="utf-8"))
    )
    assert {role.id for role in catalog.roles} == set(mappings.roles)


def test_compiled_catalog_strips_advisory_authority() -> None:
    catalog = SubagentsCatalog.model_validate_json(
        (ROLE_MAPPINGS.parent.parent.parent / "packages" / "subagents" / "dist" / "catalog.json")
        .read_text(encoding="utf-8")
    )
    mappings = RoleMappings.model_validate(
        yaml.safe_load(ROLE_MAPPINGS.read_text(encoding="utf-8"))
    )
    compiled = CompiledCatalog.from_reviewed(catalog, mappings)
    assert len(compiled.roles) == len(catalog.roles)
    for role in compiled.roles:
        assert not hasattr(role, "model_hint")
        assert not hasattr(role, "advisory_tools")
        assert set(role.tools) <= {"qmd_search", "qmd_get", "project_test"}
