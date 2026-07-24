"""The ``ae appliance`` management command group.

Wires the deployment orchestrators (product metadata, config, backup, doctor) into a
Typer surface. Configuration, backup, doctor, and version commands run without a live
runtime; container-lifecycle commands (status/logs/update/…) require a running appliance
and report that clearly unless invoked on a provisioned host.
"""

import json
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

import typer
import yaml

from aegis.deploy.backup import BackupService
from aegis.deploy.config import ConfigError, appliance_json_schema, diff_config, init_config, validate_config
from aegis.deploy.doctor import doctor, repair
from aegis.deploy.product import load_product_metadata

appliance_app = typer.Typer(no_args_is_help=True, help="Appliance lifecycle and management.")
config_app = typer.Typer(no_args_is_help=True, help="Appliance configuration.")
backup_app = typer.Typer(no_args_is_help=True, help="Backup and restore.")
appliance_app.add_typer(config_app, name="config")
appliance_app.add_typer(backup_app, name="backup")

_LIVE_HINT = "requires a running appliance; set AEGIS_LIVE_DOCKER on a provisioned host"


def _require_live(command: str) -> None:
    typer.echo(json.dumps({"ok": False, "command": command, "error": _LIVE_HINT}), err=True)
    raise typer.Exit(code=2)


def _package_version() -> str:
    try:
        return package_version("aegis-control-plane")
    except PackageNotFoundError:  # pragma: no cover - always installed in dev
        return "unknown"


@appliance_app.command("version")
def version() -> None:
    """Print the product and package version."""
    product = load_product_metadata()
    typer.echo(f"{product.display_name} {_package_version()}")


@appliance_app.command("schema")
def schema() -> None:
    """Emit the appliance configuration JSON schema."""
    typer.echo(json.dumps(appliance_json_schema(), indent=2, sort_keys=True))


# ── container lifecycle (live) ────────────────────────────────────────────────
@appliance_app.command("status")
def status() -> None:
    _require_live("status")


@appliance_app.command("ps")
def ps() -> None:
    _require_live("ps")


@appliance_app.command("logs")
def logs(service: str = typer.Argument(None), follow: bool = typer.Option(False, "--follow")) -> None:
    _require_live("logs")


@appliance_app.command("restart")
def restart(service: str = typer.Argument(None)) -> None:
    _require_live("restart")


@appliance_app.command("shell")
def shell(service: str = typer.Argument(...)) -> None:
    _require_live("shell")


@appliance_app.command("exec")
def exec_(service: str = typer.Argument(...)) -> None:
    _require_live("exec")


@appliance_app.command("inspect")
def inspect(service: str = typer.Argument(...)) -> None:
    _require_live("inspect")


@appliance_app.command("update")
def update(
    check: bool = typer.Option(False, "--check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    target_version: str = typer.Option(None, "--version"),
    channel: str = typer.Option("stable", "--channel"),
) -> None:
    _require_live("update")


@appliance_app.command("rollback")
def rollback() -> None:
    _require_live("rollback")


@appliance_app.command("restore")
def restore(backup: str = typer.Argument(...)) -> None:
    _require_live("restore")


@appliance_app.command("support-bundle")
def support_bundle() -> None:
    _require_live("support-bundle")


@appliance_app.command("uninstall")
def uninstall(purge_data: bool = typer.Option(False, "--purge-data")) -> None:
    _require_live("uninstall")


@appliance_app.command("repair")
def repair_cmd(checks: str = typer.Option(None, "--checks", help="JSON file of check results")) -> None:
    if checks is None:
        _require_live("repair")
        return
    data = json.loads(Path(checks).read_text(encoding="utf-8"))
    result = repair(doctor(data))
    typer.echo(json.dumps({"changed": result.changed, "manual": result.manual}, sort_keys=True))


@appliance_app.command("doctor")
def doctor_cmd(checks: str = typer.Option(None, "--checks", help="JSON file of check results")) -> None:
    if checks is None:
        _require_live("doctor")
        return
    data = json.loads(Path(checks).read_text(encoding="utf-8"))
    report = doctor(data)
    typer.echo(json.dumps({"ok": report.ok, "failures": report.failures()}, sort_keys=True))
    raise typer.Exit(code=0 if report.ok else 1)


# ── configuration ─────────────────────────────────────────────────────────────
@config_app.command("init")
def config_init() -> None:
    """Print a default appliance configuration."""
    typer.echo(yaml.safe_dump(init_config().model_dump(mode="json"), sort_keys=True))


@config_app.command("edit")
def config_edit() -> None:
    _require_live("config edit")


@config_app.command("apply")
def config_apply() -> None:
    _require_live("config apply")


@config_app.command("validate")
def config_validate(file: str = typer.Option(..., "--file")) -> None:
    """Validate an appliance configuration file."""
    data = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
    try:
        config = validate_config(data)
    except ConfigError as error:
        typer.echo(json.dumps({"ok": False, "error": str(error)}), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps({"ok": True, "nonsecret_digest": config.nonsecret_digest()}))


@config_app.command("diff")
def config_diff(a: str = typer.Option(..., "--a"), b: str = typer.Option(..., "--b")) -> None:
    left = validate_config(yaml.safe_load(Path(a).read_text(encoding="utf-8")))
    right = validate_config(yaml.safe_load(Path(b).read_text(encoding="utf-8")))
    typer.echo(json.dumps(diff_config(left, right), sort_keys=True))


# ── backup ────────────────────────────────────────────────────────────────────
@backup_app.command("create")
def backup_create(
    source: str = typer.Option(..., "--source"),
    dest: str = typer.Option(..., "--dest"),
) -> None:
    archive = BackupService().create(Path(source), Path(dest))
    typer.echo(json.dumps({"ok": True, "archive": str(archive)}))


@backup_app.command("verify")
def backup_verify(archive: str = typer.Option(..., "--archive")) -> None:
    ok = BackupService().verify(Path(archive))
    typer.echo(json.dumps({"ok": ok}))
    raise typer.Exit(code=0 if ok else 1)
