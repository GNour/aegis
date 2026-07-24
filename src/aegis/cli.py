import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)
companions_app = typer.Typer(no_args_is_help=True, help="Companion package commands.")
app.add_typer(companions_app, name="companions")
config_app = typer.Typer(no_args_is_help=True, help="Flow/routing configuration commands.")
app.add_typer(config_app, name="config")
flow_app = typer.Typer(no_args_is_help=True, help="Flow simulation commands.")
app.add_typer(flow_app, name="flow")
execution_app = typer.Typer(no_args_is_help=True, help="Execution/worker commands.")
app.add_typer(execution_app, name="execution")

_ROOT = Path(__file__).resolve().parents[2]


def _json_safe(value: object) -> object:
    """Recursively unwrap FrozenJsonMapping's MappingProxyType/tuple into JSON-safe types."""
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@app.callback()
def main() -> None:
    """Aegis control-plane commands."""


@app.command()
def version() -> None:
    typer.echo("Aegis 0.2.0-dev")


@companions_app.command("verify")
def companions_verify() -> None:
    """Emit a bounded JSON readiness verdict for the pinned companions."""
    from aegis.companions.digests import artifact_sha256
    from aegis.companions.lock import CompanionSourceError, verify_sources
    from aegis.companions.readiness import evaluate, load_lock

    lock = load_lock(_ROOT)
    try:
        verify_sources(_ROOT, lock, require_present=True)
        sources_clean = True
    except CompanionSourceError:
        sources_clean = False

    payload = evaluate(
        lock,
        promptx_artifact_digest=artifact_sha256(_ROOT / "packages" / "promptx" / "dist"),
        subagents_artifact_digest=artifact_sha256(_ROOT / "packages" / "subagents" / "dist"),
        sources_clean=sources_clean,
    )
    typer.echo(json.dumps(payload, sort_keys=True))
    raise typer.Exit(code=0 if payload["ready"] else 1)


@config_app.command("validate")
def config_validate(
    root: str = typer.Option("config", help="Configuration catalog root directory"),
) -> None:
    """Parse, cross-validate, and report the compiled catalog's canonical hash."""
    from aegis.config.catalog import CatalogError, build_catalog

    try:
        catalog = build_catalog(Path(root))
    except CatalogError as error:
        typer.echo(json.dumps({"ok": False, "error": str(error)}, sort_keys=True), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "catalog_hash": catalog.canonical_hash,
                "flows": sorted(catalog.flows),
            },
            sort_keys=True,
        )
    )


@flow_app.command("simulate")
def flow_simulate(
    root: str = typer.Option("config", help="Configuration catalog root directory"),
    fixture: str = typer.Option(..., help="Path to a JSON fixture request"),
) -> None:
    """Simulate flow selection for a fixture request. Creates no state."""
    from aegis.config.catalog import CatalogError, build_catalog
    from aegis.config.simulate import SimulationError, simulate

    try:
        catalog = build_catalog(Path(root))
        request = json.loads(Path(fixture).read_text(encoding="utf-8"))
        result = simulate(catalog, request)
    except (CatalogError, SimulationError) as error:
        typer.echo(json.dumps({"ok": False, "error": str(error)}, sort_keys=True), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "flow_id": result.flow.doc.id,
                "evaluated_rule_ids": list(result.evaluated_rule_ids),
                "matched_rule_id": result.matched_rule_id,
                "added_risk": result.added_risk,
                "added_gates": list(result.added_gates),
                "snapshot": _json_safe(result.flow.snapshot()),
            },
            sort_keys=True,
        )
    )


@execution_app.command("manifest-schema")
def execution_manifest_schema(
    check: bool = typer.Option(
        False, "--check", help="Exit nonzero if the committed schema is stale."
    ),
) -> None:
    """Emit (or check) the canonical project-manifest JSON schema."""
    from aegis.execution.project_manifest import manifest_json_schema

    schema_path = _ROOT / "config" / "schemas" / "project-v1.json"
    rendered = json.dumps(manifest_json_schema(), indent=2, sort_keys=True) + "\n"
    if check:
        current = schema_path.read_text(encoding="utf-8") if schema_path.exists() else ""
        if current != rendered:
            typer.echo("project-v1.json is stale; run 'ae execution manifest-schema'", err=True)
            raise typer.Exit(code=1)
        typer.echo("project-v1.json is up to date")
        return
    schema_path.write_text(rendered, encoding="utf-8")
    typer.echo(f"wrote {schema_path}")
