from typer.testing import CliRunner

from harness.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "harness 0.1.0-dev"
