"""Config catalog: parsing, cross-reference resolution, reload, and fail-closed cases."""

import shutil
from pathlib import Path

import pytest

from aegis.config.catalog import CatalogError, CatalogManager, build_catalog

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_CONFIG = REPO_ROOT / "config"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A working copy of the real, valid config tree (isolated per test)."""
    dest = tmp_path / "config"
    shutil.copytree(REAL_CONFIG, dest)
    return dest


# ── happy path ────────────────────────────────────────────────────────────────
def test_real_config_builds_and_resolves_every_reference(config_dir: Path) -> None:
    catalog = build_catalog(config_dir)
    assert set(catalog.flows) == {"feature-delivery"}
    assert set(catalog.roles) == {"tech-lead", "python-dev", "qa-engineer"}
    assert set(catalog.stages) == {"plan", "implement", "verify"}
    flow = catalog.flow("feature-delivery")
    assert [stage.doc.id for stage in flow.stages] == ["plan", "implement", "verify"]
    assert len(catalog.canonical_hash) == 64


def test_task_snapshot_survives_reload(config_dir: Path) -> None:
    manager = CatalogManager.load(config_dir)
    snapshot = manager.current.flow("feature-delivery").snapshot()
    config_dir.joinpath("flows", "feature-delivery.yaml").write_text("invalid: true")
    assert manager.reload() is False
    assert manager.current.flow("feature-delivery").snapshot() == snapshot


def test_successful_reload_swaps_the_catalog(config_dir: Path) -> None:
    manager = CatalogManager.load(config_dir)
    first_hash = manager.current.canonical_hash
    config_dir.joinpath("routing.yaml").write_text(
        (config_dir / "routing.yaml").read_text().replace("priority: 10", "priority: 20")
    )
    assert manager.reload() is True
    assert manager.current.canonical_hash != first_hash


def test_snapshot_is_deterministic_across_rebuilds(config_dir: Path) -> None:
    first = build_catalog(config_dir).flow("feature-delivery").snapshot()
    second = build_catalog(config_dir).flow("feature-delivery").snapshot()
    assert first == second


# ── unresolved references ──────────────────────────────────────────────────────
def test_role_with_unresolved_model_alias_is_rejected(config_dir: Path) -> None:
    path = config_dir / "roles" / "tech-lead.yaml"
    path.write_text(path.read_text().replace("model_alias: planning", "model_alias: ghost-alias"))
    with pytest.raises(CatalogError, match="unresolved model alias"):
        build_catalog(config_dir)


def test_stage_with_unresolved_role_is_rejected(config_dir: Path) -> None:
    path = config_dir / "stages" / "plan.yaml"
    path.write_text(path.read_text().replace("id: tech-lead", "id: ghost-role"))
    with pytest.raises(CatalogError, match="unresolved role"):
        build_catalog(config_dir)


def test_flow_with_unresolved_stage_is_rejected(config_dir: Path) -> None:
    path = config_dir / "flows" / "feature-delivery.yaml"
    path.write_text(path.read_text().replace("id: implement", "id: ghost-stage"))
    with pytest.raises(CatalogError, match="unresolved stage"):
        build_catalog(config_dir)


def test_routing_rule_with_unresolved_flow_is_rejected(config_dir: Path) -> None:
    path = config_dir / "routing.yaml"
    path.write_text(
        path.read_text().replace("select_flow: feature-delivery", "select_flow: ghost-flow")
    )
    with pytest.raises(CatalogError, match="unresolved flow"):
        build_catalog(config_dir)


def test_capability_profile_below_min_version_is_rejected(config_dir: Path) -> None:
    path = config_dir / "roles" / "tech-lead.yaml"
    path.write_text(path.read_text().replace("min_version: 1", "min_version: 99"))
    with pytest.raises(CatalogError, match="below min_version"):
        build_catalog(config_dir)


# ── duplicates ──────────────────────────────────────────────────────────────────
def test_duplicate_role_id_across_files_is_rejected(config_dir: Path) -> None:
    shutil.copy(config_dir / "roles" / "tech-lead.yaml", config_dir / "roles" / "tech-lead-2.yaml")
    with pytest.raises(CatalogError, match="document id"):
        build_catalog(config_dir)


# ── cycles ──────────────────────────────────────────────────────────────────────
def test_stage_fallback_cycle_is_rejected(config_dir: Path) -> None:
    plan = config_dir / "stages" / "plan.yaml"
    plan.write_text(plan.read_text() + "fallback_stage: implement\n")
    implement = config_dir / "stages" / "implement.yaml"
    implement.write_text(
        implement.read_text().replace("fallback_stage: plan", "fallback_stage: plan")
    )
    with pytest.raises(CatalogError, match="cyclic stage fallback"):
        build_catalog(config_dir)


def test_flow_fallback_self_reference_is_rejected(config_dir: Path) -> None:
    path = config_dir / "flows" / "feature-delivery.yaml"
    path.write_text(path.read_text() + "fallback_flow: feature-delivery\n")
    with pytest.raises(Exception, match="cannot fall back to itself"):
        build_catalog(config_dir)


# ── mandatory gates and arbitrary fields ────────────────────────────────────────
def test_flow_missing_mandatory_gate_is_rejected(config_dir: Path) -> None:
    path = config_dir / "flows" / "feature-delivery.yaml"
    path.write_text(
        path.read_text().replace("gates:\n  - qa-verification\n", "gates:\n  - other-gate\n")
    )
    with pytest.raises(CatalogError, match="missing mandatory gate"):
        build_catalog(config_dir)


def test_flow_cannot_contain_a_shell_command_field(config_dir: Path) -> None:
    path = config_dir / "flows" / "feature-delivery.yaml"
    path.write_text(path.read_text() + "command: rm -rf /\n")
    with pytest.raises(Exception):
        build_catalog(config_dir)


def test_stage_cannot_contain_a_shell_command_field(config_dir: Path) -> None:
    path = config_dir / "stages" / "plan.yaml"
    path.write_text(path.read_text() + "shell: echo hi\n")
    with pytest.raises(Exception):
        build_catalog(config_dir)
