"""Entry point for the decoy CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`decoy = "decoy.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import typer

from decoy import __version__
from decoy.cli.demo import DEMO_EPILOG
from decoy.cli.demo import _demo as demo_command
from decoy.cli.evidence import evidence_app
from decoy.cli.explain import EXPLAIN_EPILOG
from decoy.cli.explain import explain as explain_command
from decoy.cli.fit import FIT_EPILOG
from decoy.cli.fit import fit as fit_command
from decoy.cli.info import INFO_EPILOG
from decoy.cli.info import info as info_command
from decoy.cli.init import INIT_EPILOG, init_command
from decoy.cli.plan import PLAN_EPILOG
from decoy.cli.plan import plan as plan_command
from decoy.cli.preflight import PREFLIGHT_EPILOG
from decoy.cli.preflight import preflight as preflight_command
from decoy.cli.run import RUN_EPILOG
from decoy.cli.run import run as run_command
from decoy.cli.schema import SCHEMA_EPILOG
from decoy.cli.schema import schema as schema_command
from decoy.cli.storm import storm_app
from decoy.cli.templates import templates_app
from decoy.cli.unmask import UNMASK_EPILOG
from decoy.cli.unmask import unmask as unmask_command
from decoy.cli.validate import VALIDATE_EPILOG
from decoy.cli.validate import validate as validate_command
from decoy.cli.vault import vault_app

# Quick-start hints embedded in the root help. Picked up by Typer's
# default formatter; the `decoy info` command renders the same idea
# as a Rich Panel for first-run flair.
_ROOT_HELP = """\
Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy storm analyze data.csv     Profile a dataset for PII and risk.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy validate pipeline.yaml     Check a YAML pipeline before running.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy fit source.csv             Fit a distribution snapshot for statistical generation.
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
app.command(name="preflight", epilog=PREFLIGHT_EPILOG)(preflight_command)
app.command(name="unmask", epilog=UNMASK_EPILOG)(unmask_command)
app.command(name="fit", epilog=FIT_EPILOG)(fit_command)
app.command(name="init", epilog=INIT_EPILOG)(init_command())
app.command(name="demo", epilog=DEMO_EPILOG)(demo_command)
app.command(name="explain", epilog=EXPLAIN_EPILOG)(explain_command)
app.command(name="info", epilog=INFO_EPILOG)(info_command)
app.command(name="schema", epilog=SCHEMA_EPILOG)(schema_command)
app.add_typer(storm_app, name="storm")
app.add_typer(templates_app, name="templates")
app.add_typer(vault_app, name="vault")
app.add_typer(evidence_app, name="evidence")
app.command(name="plan", epilog=PLAN_EPILOG)(plan_command)


if __name__ == "__main__":
    app()
