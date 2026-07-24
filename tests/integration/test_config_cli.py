"""The `ae config validate` and `ae flow simulate` commands against the real config."""

import json

from typer.testing import CliRunner

from aegis.cli import app

runner = CliRunner()


def test_config_validate_reports_hash_and_flows() -> None:
    result = runner.invoke(app, ["config", "validate", "--root", "config"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["flows"] == ["feature-delivery"]
    assert len(payload["catalog_hash"]) == 64


def test_flow_simulate_reports_stages_capabilities_and_budgets() -> None:
    result = runner.invoke(
        app,
        [
            "flow",
            "simulate",
            "--root",
            "config",
            "--fixture",
            "tests/fixtures/requests/feature.json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["flow_id"] == "feature-delivery"
    assert payload["matched_rule_id"] == "feature-delivery-default"
    stages = payload["snapshot"]["stages"]
    assert [s["stage_id"] for s in stages] == ["plan", "implement", "verify"]
    assert all("capability_profile" in s and "budgets" in s for s in stages)
