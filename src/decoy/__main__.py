"""Entry point for the decoy CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`decoy = "decoy.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import os
import sys

import typer

from decoy import __version__
from decoy.cli.cockpit import DOCTOR_EPILOG, doctor
from decoy.cli.demo import DEMO_EPILOG
from decoy.cli.demo import _demo as demo_command
from decoy.cli.explain import EXPLAIN_EPILOG
from decoy.cli.explain import explain as explain_command
from decoy.cli.fit import FIT_EPILOG
from decoy.cli.fit import fit as fit_command
from decoy.cli.info import INFO_EPILOG
from decoy.cli.info import info as info_command
from decoy.cli.init import INIT_EPILOG, init_command
from decoy.cli.reference import LIST_EPILOG, SHOW_EPILOG, list_, show
from decoy.cli.report import report_app
from decoy.cli.run import RUN_EPILOG
from decoy.cli.run import run as run_command
from decoy.cli.scan import scan_app
from decoy.cli.schema import SCHEMA_EPILOG
from decoy.cli.schema import schema as schema_command
from decoy.cli.subset import SUBSET_EPILOG
from decoy.cli.subset import subset as subset_command
from decoy.cli.unmask import UNMASK_EPILOG
from decoy.cli.unmask import unmask as unmask_command
from decoy.cli.upgrade import UPGRADE_EPILOG
from decoy.cli.upgrade import upgrade as upgrade_command
from decoy.cli.validate import validate_app

# Quick-start hints embedded in the root help. Picked up by Typer's
# default formatter; the `decoy info` command renders the same idea
# as a Rich Panel for first-run flair.
_ROOT_HELP = """\
Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy scan data.csv              Profile a dataset for PII and re-id risk (candidates as suggestions).
  decoy validate pipeline.yaml     Run the whole pre-run gate (config + compile + preflight).
  decoy validate compile pipeline.yaml --explain  Explain per-column strategy and compile decisions.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy subset pipeline.yaml --dry-run   Preview a FK-aware referential subset.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy fit source.csv             Fit a distribution snapshot for statistical generation.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy upgrade                    Upgrade the managed runtime (verify + swap). --check to just look.
  decoy list templates             Browse bundled pipeline templates.
  decoy show template hipaa        Dump one bundled template to stdout.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.
  decoy report show evidence.json  Show the evidence manifest (the post-run surface: show/verify/fidelity/integrity/diff/vault).
  decoy report verify evidence.json  Re-hash the recorded files and report fingerprint drift.
  decoy report diff a.json b.json  Compare two manifests: fingerprints always, data when the output files exist.

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


def _maybe_print_update_notice() -> None:
    """Print a one-line 'new version available' notice on interactive startup.

    Fully gated and fail-silent (readiness report 4.3): suppressed with no TTY,
    under CI, on `--json` / `--quiet`, with `--no-update-check` or the opt-out
    env var, and on the `upgrade` command itself (which reports this directly).
    Cache-first with a short-timeout refresh so it never blocks a run, and wrapped
    so it can never raise into a command. The notice goes to stderr, so it never
    pollutes stdout a script may be piping."""
    try:
        from decoy import _version_endpoint

        argv = sys.argv[1:]
        if "upgrade" in argv:
            return
        line = _version_endpoint.maybe_update_notice(
            current=__version__,
            argv=argv,
            env=dict(os.environ),
            isatty=sys.stdout.isatty(),
        )
        if line:
            sys.stderr.write(line + "\n")
    except Exception:
        # A startup notice must never slow or break a real command.
        return


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the decoy CLI version and exit.",
    ),
    no_update_check: bool = typer.Option(
        False,
        "--no-update-check",
        help="Suppress the startup 'new version available' notice for this run.",
    ),
) -> None:
    """Decoy CLI."""
    # Forces Typer to treat the app as multi-command even with one subcommand,
    # so users invoke `decoy run ...` not `decoy ...`.
    _maybe_print_update_notice()


app.command(name="run", epilog=RUN_EPILOG)(run_command)
app.add_typer(validate_app, name="validate")
app.command(name="unmask", epilog=UNMASK_EPILOG)(unmask_command)
app.command(name="fit", epilog=FIT_EPILOG)(fit_command)
app.command(name="init", epilog=INIT_EPILOG)(init_command())
app.command(name="upgrade", epilog=UPGRADE_EPILOG)(upgrade_command)
app.command(name="demo", epilog=DEMO_EPILOG)(demo_command)
app.command(name="explain", epilog=EXPLAIN_EPILOG)(explain_command)
app.command(name="info", epilog=INFO_EPILOG)(info_command)
app.command(name="schema", epilog=SCHEMA_EPILOG)(schema_command)
app.add_typer(scan_app, name="scan")
app.add_typer(report_app, name="report")
app.command(name="list", epilog=LIST_EPILOG)(list_)
app.command(name="show", epilog=SHOW_EPILOG)(show)
app.command(name="doctor", epilog=DOCTOR_EPILOG)(doctor)
app.command(name="subset", epilog=SUBSET_EPILOG)(subset_command)


if __name__ == "__main__":
    app()
