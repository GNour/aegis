"""The `ae appliance` command surface exposes every documented command."""

import yaml
from typer.testing import CliRunner

from aegis.cli import app

runner = CliRunner()

APPLIANCE_COMMANDS = {
    "status",
    "ps",
    "logs",
    "restart",
    "shell",
    "exec",
    "inspect",
    "version",
    "doctor",
    "repair",
    "update",
    "rollback",
    "restore",
    "support-bundle",
    "uninstall",
    "config",
    "backup",
}


def test_appliance_help_lists_documented_commands() -> None:
    result = runner.invoke(app, ["appliance", "--help"])
    assert result.exit_code == 0
    for name in APPLIANCE_COMMANDS:
        assert name in result.stdout


def test_config_subcommands_present() -> None:
    result = runner.invoke(app, ["appliance", "config", "--help"])
    assert result.exit_code == 0
    for name in ("init", "edit", "validate", "diff", "apply"):
        assert name in result.stdout


def test_backup_subcommands_present() -> None:
    result = runner.invoke(app, ["appliance", "backup", "--help"])
    assert result.exit_code == 0
    for name in ("create", "verify"):
        assert name in result.stdout


def test_version_command_runs() -> None:
    result = runner.invoke(app, ["appliance", "version"])
    assert result.exit_code == 0
    assert "Aegis" in result.stdout


def test_config_validate_accepts_sanitized_file(tmp_path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        yaml.safe_dump({"version": 1, "exposure": {"bind_address": "127.0.0.1"}}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["appliance", "config", "validate", "--file", str(cfg)])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout


def test_config_validate_rejects_public_bind(tmp_path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        yaml.safe_dump({"version": 1, "exposure": {"bind_address": "0.0.0.0"}}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["appliance", "config", "validate", "--file", str(cfg)])
    assert result.exit_code == 1


def test_live_command_reports_requirement_without_docker() -> None:
    result = runner.invoke(app, ["appliance", "status"])
    assert result.exit_code == 2
    assert "AEGIS_LIVE_DOCKER" in result.stdout + result.stderr


def test_backup_create_and_verify_roundtrip(tmp_path) -> None:
    source = tmp_path / "data" / "state"
    source.mkdir(parents=True)
    (source / "db").write_text("x", encoding="utf-8")
    archive = tmp_path / "b.tar.gz"
    created = runner.invoke(
        app,
        ["appliance", "backup", "create", "--source", str(tmp_path / "data"), "--dest", str(archive)],
    )
    assert created.exit_code == 0
    verified = runner.invoke(app, ["appliance", "backup", "verify", "--archive", str(archive)])
    assert verified.exit_code == 0
    assert '"ok": true' in verified.stdout
