from typer.testing import CliRunner

from aegis.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Aegis 0.3.0-dev"
