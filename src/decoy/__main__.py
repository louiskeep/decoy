"""Entry point for the decoy CLI.

The Typer app is exported as `app` so the project script in pyproject.toml
(`decoy = "decoy.__main__:app"`) can call it directly without going
through `if __name__ == "__main__":`.
"""

import copy
import errno
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperGroup

from decoy import __version__
from decoy._env_flags import safe_env_flag
from decoy.cli.ci import ci_app
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
from decoy.cli.project import project_app
from decoy.cli.reference import LIST_EPILOG, SHOW_EPILOG, list_, show
from decoy.cli.report import report_app
from decoy.cli.run import RUN_EPILOG
from decoy.cli.run import run as run_command
from decoy.cli.scan import scan_app
from decoy.cli.schema import SCHEMA_EPILOG
from decoy.cli.schema import schema as schema_command
from decoy.cli.setup import SETUP_EPILOG, setup_command
from decoy.cli.subset import SUBSET_EPILOG
from decoy.cli.subset import subset as subset_command
from decoy.cli.tokenize import DETOKENIZE_EPILOG, TOKENIZE_EPILOG
from decoy.cli.tokenize import detokenize as detokenize_command
from decoy.cli.tokenize import tokenize as tokenize_command
from decoy.cli.unmask import UNMASK_EPILOG
from decoy.cli.unmask import unmask as unmask_command
from decoy.cli.upgrade import UPGRADE_EPILOG
from decoy.cli.upgrade import upgrade as upgrade_command
from decoy.cli.validate import validate_app
from decoy.ui.output import print_traceback, setup_output
from decoy.ui.theme import error, hint

# Quick-start hints embedded in the root help. Picked up by Typer's
# default formatter; the `decoy info` command renders the same idea
# as a Rich Panel for first-run flair.
_ROOT_HELP = """\
Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy scan data.csv --has-header Profile a dataset for PII and re-id risk (candidates as suggestions).
  decoy validate pipeline.yaml     Run the whole pre-run gate (config + compile + preflight).
  decoy validate compile pipeline.yaml --explain  Explain per-column strategy and compile decisions.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy subset pipeline.yaml --dry-run   Preview a FK-aware referential subset.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy tokenize pipeline.yaml --vault tokens.db   Reversible tokenization: mask tokenize columns + write a local vault.
  decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db   Reverse a tokenized file from the local vault.
  decoy fit source.csv             Fit a distribution snapshot for statistical generation.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy setup                      Set this box's max memory and threads for `decoy run`.
  decoy project new acme           Make a project folder for one client's pipelines and outputs.
  decoy list templates             Browse bundled pipeline templates.
  decoy show template hipaa        Dump one bundled template to stdout.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.
  decoy report show evidence.json  Show the evidence manifest (the post-run surface: show/verify/fidelity/integrity/diff/vault).
  decoy report verify evidence.json  Re-hash the recorded files and report fingerprint drift.
  decoy report diff a.json b.json  Compare two manifests: fingerprints always, data when the output files exist.
  decoy ci check                   Run CI checks from .decoy-ci.yaml; JSON, SARIF, or Markdown report (see docs/ci-contracts.md).

Run `decoy --install-completion` to enable shell tab completion.
"""

# Typer's usage-error base (bad flag, unknown command, BadParameter), taken from a public
# export so the guard never imports Typer's bundled Click package.
_USAGE_ERROR = typer.BadParameter.__base__

# Exceptions Click and Typer already turn into a clean exit. The guard must not touch them.
_PASS_THROUGH = (typer.Exit, typer.Abort, _USAGE_ERROR, EOFError)


_SEEN_CTXS = "decoy.guard.contexts"


def _record_contexts(cmd: Any) -> Any:
    """Return a shallow copy of `cmd` that records every context Click builds for it.

    The crash guard reads `--verbose` from what Click parsed, never from raw tokens: after
    `--` the same text is a positional value, and an option value can equal `-v`. `ctx.meta`
    is shared down the context chain, so one list collects the root and every sub-command.
    """
    wrapped = copy.copy(cmd)
    # Bound to the copy, not to `cmd`: the context Click builds must point at the copy so
    # its `resolve_command` (below) runs for nested groups too. Binding to the original
    # would make Click invoke the original group and skip every deeper recording.
    original = type(cmd).make_context.__get__(wrapped)

    def make_context(info_name: Any, args: Any, parent: Any = None, **extra: Any) -> Any:
        sub = original(info_name, args, parent=parent, **extra)
        sub.meta.setdefault(_SEEN_CTXS, []).append(sub)
        return sub

    wrapped.make_context = make_context
    if isinstance(cmd, TyperGroup):
        inner = type(cmd).resolve_command.__get__(wrapped)

        def resolve_command(ctx: Any, args: list[str]) -> Any:
            name, found, rest = inner(ctx, args)
            return name, _record_contexts(found) if found is not None else found, rest

        wrapped.resolve_command = resolve_command
    return wrapped


def _parsed_verbose(ctx: Any) -> bool:
    # A crash before parsing finished leaves no parsed value, which counts as not verbose.
    seen = ctx.meta.get(_SEEN_CTXS, [])
    return any(bool(c.params.get("verbose")) for c in seen)


class _GuardedGroup(TyperGroup):
    """Root group that keeps a Python traceback from reaching the user.

    An unexpected `Exception` from any command prints `error: internal error (<ClassName>)`
    and exits 1. `--verbose` adds the traceback; `DECOY_DEBUG=1` re-raises untouched (the
    test suite sets it). `KeyboardInterrupt` and `SystemExit` are not `Exception`s and go to
    Click as before. A closed pipe (EPIPE) also goes to Click; every other `OSError` is a crash.
    """

    def resolve_command(self, ctx: Any, args: list[str]) -> Any:
        name, cmd, rest = super().resolve_command(ctx, args)
        return name, _record_contexts(cmd) if cmd is not None else cmd, rest

    def invoke(self, ctx: Any) -> Any:
        # Read here, in the crash handler, so it cannot raise. Tracebacks can hold row data,
        # so an unknown spelling leaves debug off.
        debug = safe_env_flag("DECOY_DEBUG", default=False, unknown=False)
        try:
            return super().invoke(ctx)
        except _PASS_THROUGH:
            raise
        except Exception as exc:
            if isinstance(exc, OSError) and exc.errno == errno.EPIPE:
                raise
            if debug:
                raise
            name = type(exc).__name__
            verbose = _parsed_verbose(ctx)
            state = setup_output(json_=False, quiet=False, verbose=verbose)
            state.err_console.print(error("error:"), f"internal error ({name})")
            state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback."
            )
            if verbose:
                state.err_console.print(
                    hint("(--verbose: traceback below; diagnostic output may contain row data)")
                )
                print_traceback(state)
        # Raised outside the `except` block so the safe exit carries neither the original
        # exception as __cause__ nor as __context__.
        raise typer.Exit(1)


# The generation path in one place: `fit` is in the Generate panel, but `run` and the fidelity
# report sit in other panels, so a user scanning the panels would not see the three together.
_ROOT_EPILOG = (
    "Generate synthetic data: decoy fit source.csv, then decoy run pipeline.yaml, then "
    "decoy report fidelity <source.csv> <synthetic.csv> --generate. "
    "Details: decoy explain generation."
)


app = typer.Typer(
    name="decoy",
    cls=_GuardedGroup,
    help=_ROOT_HELP,
    epilog=_ROOT_EPILOG,
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=False,
)


_NO_NOTICE_COMMANDS = frozenset({"upgrade"})


def _key_unresolved() -> bool:
    from decoy.distribution import release_key

    try:
        release_key.pinned_public_pem()
    except release_key.NoPinnedKeyError:
        return True
    except OSError:
        return False
    return False


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"decoy {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
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
        help="Suppress the 'new version available' startup notice.",
    ),
    project: Path | None = typer.Option(
        None,
        "--project",
        help=(
            "Project folder for pipeline names (default: DECOY_PROJECT, else the nearest "
            "decoy.yaml above the current folder)."
        ),
    ),
) -> None:
    """Decoy CLI."""
    # Forces Typer to treat the app as multi-command even with one subcommand,
    # so users invoke `decoy run ...` not `decoy ...`.
    #
    # Startup update notice (readiness 4.3): interactive only, once per cadence
    # window, non-blocking, fail-silent, opt-out. It writes at most one line to
    # stderr and never affects a command's result. Imported lazily so a bare
    # `import decoy` / `--version` pays nothing for it.
    from decoy import _update_check
    from decoy.cli.exit_codes import EXIT_RUNTIME
    from decoy.distribution import runtime_guard

    # Managed runtime only: a companion removed or ABI-mismatched after install is a loud
    # refusal at run time too, not just at install (`upgrade` stays runnable to repair it).
    refusal = runtime_guard.enforce(ctx.invoked_subcommand)
    if refusal is not None:
        typer.echo(f"decoy: {refusal}", err=True)
        raise typer.Exit(code=EXIT_RUNTIME)

    # `upgrade` owns its own key and network ordering (placeholder-key refusal and local
    # rollback precede any network), and an unresolved placeholder key means this build
    # cannot act on a notice, so the startup probe never runs ahead of either.
    _update_check.maybe_print_notice(
        suppress=no_update_check
        or ctx.invoked_subcommand in _NO_NOTICE_COMMANDS
        or _key_unresolved()
    )


app.command(name="run", rich_help_panel="Run", epilog=RUN_EPILOG)(run_command)
app.add_typer(validate_app, name="validate", rich_help_panel="Check and report")
app.command(name="unmask", rich_help_panel="Mask", epilog=UNMASK_EPILOG)(unmask_command)
app.command(name="tokenize", rich_help_panel="Mask", epilog=TOKENIZE_EPILOG)(tokenize_command)
app.command(name="detokenize", rich_help_panel="Mask", epilog=DETOKENIZE_EPILOG)(detokenize_command)
app.command(name="fit", rich_help_panel="Generate", epilog=FIT_EPILOG)(fit_command)
app.command(name="init", rich_help_panel="Start", epilog=INIT_EPILOG)(init_command())
app.command(name="demo", rich_help_panel="Start", epilog=DEMO_EPILOG)(demo_command)
app.command(name="explain", rich_help_panel="Reference", epilog=EXPLAIN_EPILOG)(explain_command)
app.command(name="info", rich_help_panel="Start", epilog=INFO_EPILOG)(info_command)
app.command(name="schema", rich_help_panel="Reference", epilog=SCHEMA_EPILOG)(schema_command)
app.add_typer(project_app, name="project", rich_help_panel="Start")
app.add_typer(scan_app, name="scan", rich_help_panel="Mask")
app.add_typer(report_app, name="report", rich_help_panel="Check and report")
app.add_typer(ci_app, name="ci", rich_help_panel="Check and report")
app.command(name="list", rich_help_panel="Reference", epilog=LIST_EPILOG)(list_)
app.command(name="show", rich_help_panel="Reference", epilog=SHOW_EPILOG)(show)
app.command(name="doctor", rich_help_panel="Start", epilog=DOCTOR_EPILOG)(doctor)
app.command(name="setup", rich_help_panel="Start", epilog=SETUP_EPILOG)(setup_command)
app.command(name="subset", rich_help_panel="Run", epilog=SUBSET_EPILOG)(subset_command)
app.command(name="upgrade", rich_help_panel="Start", epilog=UPGRADE_EPILOG)(upgrade_command)


if __name__ == "__main__":
    app()
