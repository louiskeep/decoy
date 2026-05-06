"""Entry point for the decoy CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`decoy = "decoy.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import typer

from decoy import __version__
from decoy.cli.demo import DEMO_EPILOG, _demo as demo_command
from decoy.cli.forecast import forecast_app
from decoy.cli.init import INIT_EPILOG, init_command
from decoy.cli.run import RUN_EPILOG, run as run_command
from decoy.cli.storm import storm_app
from decoy.cli.validate import VALIDATE_EPILOG, validate as validate_command

app = typer.Typer(
    name="decoy",
    help=(
        "Decoy -- data masking and synthetic generation CLI. "
        "Run `decoy --install-completion` to enable shell tab completion."
    ),
    no_args_is_help=True,
    add_completion=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"decoy {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the decoy CLI version and exit.",
    ),
) -> None:
    """Decoy CLI."""
    # Forces Typer to treat the app as multi-command even with one subcommand,
    # so users invoke `decoy run ...` not `decoy ...`.


app.command(name="run", epilog=RUN_EPILOG)(run_command)
app.command(name="validate", epilog=VALIDATE_EPILOG)(validate_command)
app.command(name="init", epilog=INIT_EPILOG)(init_command())
app.command(name="demo", epilog=DEMO_EPILOG)(demo_command)
app.add_typer(storm_app, name="storm")
app.add_typer(forecast_app, name="forecast")


if __name__ == "__main__":
    app()
