"""Entry point for the decoy CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`decoy = "decoy.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import typer

from decoy import __version__
from decoy.cli.demo import DEMO_EPILOG, _demo as demo_command
from decoy.cli.explain import EXPLAIN_EPILOG, explain as explain_command
from decoy.cli.forecast import forecast_app
from decoy.cli.info import INFO_EPILOG, info as info_command
from decoy.cli.init import INIT_EPILOG, init_command
from decoy.cli.run import RUN_EPILOG, run as run_command
from decoy.cli.storm import storm_app
from decoy.cli.templates import templates_app
from decoy.cli.validate import VALIDATE_EPILOG, validate as validate_command

# Quick-start hints embedded in the root help. Picked up by Typer's
# default formatter; the `decoy info` command renders the same idea
# as a Rich Panel for first-run flair.
_ROOT_HELP = """\
Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy storm scan data.csv        Profile a dataset for PII and risk.
  decoy forecast recommend scan.json   Recommend a Disguise from a scan.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy validate pipeline.yaml     Check a YAML pipeline before running.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy templates list             Browse bundled pipeline templates.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.

Run `decoy --install-completion` to enable shell tab completion.
"""

app = typer.Typer(
    name="decoy",
    help=_ROOT_HELP,
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
app.command(name="explain", epilog=EXPLAIN_EPILOG)(explain_command)
app.command(name="info", epilog=INFO_EPILOG)(info_command)
app.add_typer(storm_app, name="storm")
app.add_typer(forecast_app, name="forecast")
app.add_typer(templates_app, name="templates")


if __name__ == "__main__":
    app()
