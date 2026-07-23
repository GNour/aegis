import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Aegis control-plane commands."""


@app.command()
def version() -> None:
    typer.echo("Aegis 0.1.0-dev")
