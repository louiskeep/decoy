"""Bundled starter-pipeline readers (dispatched from `decoy list templates`
and `decoy show template NAME`).

Lets users see what templates ship without running `decoy init`, and
pipe a template directly to a file:

    decoy show template hipaa > pipeline.yaml

The same templates back the preset prompts in `decoy init`.
"""

from __future__ import annotations

import sys
from difflib import get_close_matches

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.templates import get_template, list_templates, template_names
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint


def _list(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON list of {name, summary} objects instead of a table.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List every bundled pipeline template."""
    state = setup_output(json_, quiet, verbose)
    templates = list_templates()

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "list templates",
                "status": "ok",
                "templates": [{"name": t.name, "summary": t.summary} for t in templates],
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent("Bundled templates:"))
    table = make_table("Name", "Summary")
    for t in templates:
        table.add_row(t.name, t.summary)
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "dump one to stdout with",
        code("decoy show template <name>") + ".",
    )


def _show(
    name: str = typer.Argument(
        ...,
        help="Which template to print. Tab-completes from the bundled set.",
        autocompletion=template_names,
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Wrap the body in a JSON envelope instead of printing raw YAML.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Print one bundled template to stdout.

    Default mode prints raw YAML so it pipes cleanly to a file:
    `decoy show template hipaa > pipeline.yaml`. Wrap in --json when a
    script needs the metadata too.
    """
    state = setup_output(json_, quiet, verbose)

    template = get_template(name)
    if template is None:
        guess = get_close_matches(name, template_names(), n=1, cutoff=0.5)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "show template",
                    "status": "error",
                    "name": name,
                    "error": f"unknown template {name!r}",
                    "did_you_mean": guess[0] if guess else None,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"unknown template {name!r}.")
            if guess:
                state.err_console.print(" ", hint("hint:"), "did you mean", code(guess[0]) + "?")
            else:
                state.err_console.print(
                    " ",
                    hint("hint:"),
                    "list every template with",
                    code("decoy list templates") + ".",
                )
        raise typer.Exit(code=EXIT_USAGE)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "show template",
                "status": "ok",
                "name": template.name,
                "summary": template.summary,
                "body": template.body,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    # Default mode: raw YAML to stdout. Skipping state.console.print here
    # keeps Rich from wrapping/highlighting the YAML body so users can pipe
    # it straight into a file with `decoy show template hipaa > p.yaml`.
    sys.stdout.write(template.body)
    if not template.body.endswith("\n"):
        sys.stdout.write("\n")
