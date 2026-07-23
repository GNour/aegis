import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Harness control-plane commands."""


@app.command()
def version() -> None:
    typer.echo("harness 0.1.0-dev")
