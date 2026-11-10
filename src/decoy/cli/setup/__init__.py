"""`decoy setup`: write this box's settings (`$DECOY_HOME/settings.json`)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import typer

from decoy import _resources as host
from decoy._atomic import AtomicWriteError, describe
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.setup._sections import SECTIONS
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import accent, error, hint, success

SETUP_EPILOG = """\
Examples:

  decoy setup                 Confirm each value, then write the settings file.

  decoy setup --yes           Write this host's detected values without asking.

  decoy setup --yes --json    Same, with a machine-readable result.
"""


def _prompt(label: str, default: str, check: Callable[[str], Any]) -> Any:
    return typer.prompt(label, default=default, value_proc=check)


def setup_command(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept the detected or stored values; do not prompt."
    ),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON result instead of text."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs on stderr."),
) -> None:
    """Set this box's max memory and threads for `decoy run`.

    Shows what this host reports, asks you to confirm or change it, and writes
    $DECOY_HOME/settings.json (default ~/.decoy/settings.json). A flag or environment
    variable on a single run still wins over the file.
    """
    state = setup_output(json_, quiet, verbose)
    if not yes and not sys.stdin.isatty():
        state.err_console.print(error("error:"), "setup needs a terminal; pass --yes to accept.")
        raise typer.Exit(code=EXIT_USAGE)
    try:
        stored = host.read_settings()
    except host.ResourceError:
        stored = {}  # an unusable file is replaced, not trusted
    doc: dict[str, Any] = {"schema_version": host.SCHEMA_VERSION}
    written: dict[str, Any] = {}
    try:
        for section in SECTIONS:
            proposed = section.propose(stored)
            if not yes:
                state.console.print(accent(section.title))
            values = proposed if yes else section.ask(proposed, _prompt)
            written[section.name] = values
            doc[section.name] = section.render(values)
        path = host.write_settings(json.dumps(doc, indent=2) + "\n")
    except host.ResourceError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_USAGE) from None
    except AtomicWriteError as exc:
        state.err_console.print(error("error:"), "settings not written:", describe(exc))
        state.err_console.print(" ", hint("hint:"), "check the directory is writable.")
        raise typer.Exit(code=EXIT_RUNTIME) from None
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "setup",
                "status": "ok",
                "settings_path": str(path),
                "schema_version": host.SCHEMA_VERSION,
                "sections": written,
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.console.print(success("Wrote"), str(path))
