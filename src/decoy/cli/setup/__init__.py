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
from decoy.distribution import lock
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import accent, error, hint, success

SETTINGS_LOCK = ".settings.lock"
# Only an unreadable or non-JSON/non-object file is replaced; anything else is the user's data.
_UNUSABLE = frozenset({"unreadable", "invalid"})


def _busy() -> Exception:
    return host.ResourceError("settings.json", "busy")


SETUP_EPILOG = """\
Examples:

  decoy setup                 Confirm each value, then write the settings file.

  decoy setup --yes           Write this host's detected values without asking.

  decoy setup --yes --json    Same, with a machine-readable result.
"""


def _prompt(label: str, default: str, check: Callable[[str], Any]) -> Any:
    return typer.prompt(label, default=default, value_proc=check)


def _version(existing: dict[str, Any] | None) -> str:
    """Our schema version, unless the file already holds a higher minor of major 1."""
    stored = (existing or {}).get("schema_version", "")
    if stored and int(stored.split(".")[1]) > int(host.SCHEMA_VERSION.split(".")[1]):
        return stored
    return host.SCHEMA_VERSION


def setup_command(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept the detected or stored values; do not prompt."
    ),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON result instead of text."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs on stderr."),
) -> None:
    """Set this box's max memory and threads for `decoy run`.

    Shows what this host reports, asks you to confirm or change it, and writes
    $DECOY_HOME/settings.json (default ~/.decoy/settings.json). Other sections and keys
    already in the file are kept. A flag or environment variable on a single run still
    wins over the file.
    """
    state = setup_output(json_, quiet, verbose)
    if not yes and not sys.stdin.isatty():
        state.err_console.print(error("error:"), "setup needs a terminal; pass --yes to accept.")
        raise typer.Exit(code=EXIT_USAGE)
    try:
        stored = host.read_settings()
    except host.ResourceError:
        stored = {}
    written: dict[str, Any] = {}
    replaced = False
    try:
        proposals = []
        for section in SECTIONS:
            proposed = section.propose(stored)
            if not yes:
                state.console.print(accent(section.title))
            values = proposed if yes else section.ask(proposed, _prompt)
            written[section.name] = values
            proposals.append((section, values))
        # The file is read again under the lock, so a change made while the user answered
        # the prompts is merged, not lost. The lock serializes decoy processes only; an
        # editor or another tool writing the file is outside its reach.
        with lock.exclusive(host.decoy_home(), SETTINGS_LOCK, _busy):
            try:
                existing = host.load_document()
            except host.ResourceError as exc:
                if exc.code not in _UNUSABLE:
                    raise  # a readable document we do not understand is refused, never replaced
                existing, replaced = None, True
            doc: dict[str, Any] = dict(existing or {})
            doc["schema_version"] = _version(existing)
            for section, values in proposals:
                # Keys this section does not own, and other top-level sections, stay as they were.
                owned = doc.get(section.name)
                rendered = section.render(values)
                doc[section.name] = {**(owned if isinstance(owned, dict) else {}), **rendered}
            path = host.write_settings(json.dumps(doc, indent=2) + "\n")
    except host.ResourceError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_USAGE) from None
    except AtomicWriteError as exc:
        state.err_console.print(error("error:"), "settings not written:", describe(exc))
        state.err_console.print(" ", hint("hint:"), "check the directory is writable.")
        raise typer.Exit(code=EXIT_RUNTIME) from None
    except OSError:
        # Creating the settings lock (or its folder) failed; nothing was written.
        state.err_console.print(
            error("error:"), "settings not written: the settings lock could not be created"
        )
        state.err_console.print(" ", hint("hint:"), "check the directory is writable.")
        raise typer.Exit(code=EXIT_RUNTIME) from None
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "setup",
                "status": "ok",
                "settings_path": str(path),
                "schema_version": doc["schema_version"],
                "sections": written,
                "replaced_unusable_file": replaced,
            },
        )
    elif state.mode is not OutputMode.quiet:
        if replaced:
            state.console.print(hint("note:"), "the existing settings file was unusable; replaced.")
        state.console.print(success("Wrote"), str(path))
