"""Entry point for the forge CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`forge = "forge.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import typer

from forge import __version__
from forge.cli.run import run as run_command
from forge.cli.validate import validate as validate_command

app = typer.Typer(
    name="forge",
    help="Forge — data masking and synthetic generation CLI.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"forge {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the forge CLI version and exit.",
    ),
) -> None:
    """Forge CLI."""
    # Forces Typer to treat the app as multi-command even with one subcommand,
    # so users invoke `forge run ...` not `forge ...`.


app.command(name="run")(run_command)
app.command(name="validate")(validate_command)


if __name__ == "__main__":
    app()
