"""The compiled catalog must carry only reviewed Aegis authority, never advisory hints."""

from pathlib import Path

import pytest
import yaml

from aegis.companions.catalog import compile_catalog
from aegis.companions.subagents import ALLOWED_TOOLS, RoleMappings, SubagentsCatalog

ROOT = Path(__file__).resolve().parents[1].parent
CATALOG_SRC = ROOT / "packages" / "subagents" / "dist" / "catalog.json"
MAPPINGS_SRC = ROOT / "config" / "companions" / "role-mappings.yaml"


@pytest.fixture
def result():
    catalog = SubagentsCatalog.model_validate_json(CATALOG_SRC.read_text(encoding="utf-8"))
    mappings = RoleMappings.model_validate(
        yaml.safe_load(MAPPINGS_SRC.read_text(encoding="utf-8"))
    )
    return compile_catalog(catalog, mappings)


def test_advisory_authority_is_absent(result) -> None:
    # The advisory key names must not appear at all (they are struct keys, not prose).
    rendered = result.canonical_bytes.decode("utf-8")
    assert "advisory_tools" not in rendered
    assert "model_hint" not in rendered
    # Structurally: no compiled role carries an advisory field.
    for role in result.catalog.roles:
        dumped = role.model_dump(mode="json")
        assert "model_hint" not in dumped
        assert "advisory_tools" not in dumped


def test_every_compiled_tool_is_in_the_fixed_registry(result) -> None:
    for role in result.catalog.roles:
        assert set(role.tools) <= ALLOWED_TOOLS


def test_committed_assets_match_compiler(result) -> None:
    import json

    committed = json.loads(
        (ROOT / "src" / "aegis" / "data" / "companions" / "roles.compiled.json").read_text(
            encoding="utf-8"
        )
    )
    assert committed == result.catalog.model_dump(mode="json")
