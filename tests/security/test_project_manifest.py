"""Trusted project manifests reject shell strings and dangerous service fields."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.execution.project_manifest import ProjectManifest, manifest_json_schema

_SCHEMA_FILE = Path(__file__).resolve().parents[2] / "config" / "schemas" / "project-v1.json"


def _valid_service() -> dict[str, object]:
    return {
        "image": "postgres:17",
        "healthcheck": ["pg_isready"],
        "container_port": 5432,
        "limits": {"memory_mb": 512, "cpus": 1.0},
    }


@pytest.mark.parametrize(
    "override",
    [
        {"privileged": True},
        {"network_mode": "host"},
        {"devices": ["/dev/kvm"]},
        {"volumes": ["/etc:/host"]},
        {"cap_add": ["SYS_ADMIN"]},
        {"pid": "host"},
    ],
)
def test_dangerous_service_fields_are_rejected(override: dict[str, object]) -> None:
    service = {**_valid_service(), **override}
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(
            {"version": 1, "commands": {}, "services": {"db": service}}
        )


def test_commands_are_argument_arrays() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(
            {"version": 1, "commands": {"test": "pytest && curl evil"}}
        )


def test_empty_command_argv_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"version": 1, "commands": {"test": []}})


def test_nul_byte_in_argv_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"version": 1, "commands": {"test": ["pytest\x00"]}})


def test_unsupported_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"version": 2, "commands": {}})


def test_sanitized_manifest_is_accepted() -> None:
    manifest = ProjectManifest.model_validate(
        {
            "version": 1,
            "commands": {"test": ["pytest", "-q"], "build": ["make", "build"]},
            "services": {"db": _valid_service()},
            "artifact_globs": ["dist/**"],
        }
    )
    assert manifest.commands["test"] == ("pytest", "-q")
    assert manifest.services["db"].container_port == 5432


def test_manifest_is_frozen() -> None:
    manifest = ProjectManifest.model_validate({"version": 1, "commands": {"t": ["pytest"]}})
    with pytest.raises(ValidationError):
        manifest.version = 1  # type: ignore[misc]


def test_committed_schema_matches_generated() -> None:
    committed = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    assert committed == manifest_json_schema()
