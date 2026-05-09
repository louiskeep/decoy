"""`decoy info` -- branded splash + quick-start cheat sheet.

Renders the banner Panel and a one-screen orientation. Designed as the
answer to `decoy` typed alone (when we want flair) and to be runnable
on demand. JSON mode emits version + topic / template names so scripts
can probe what the CLI knows about.
"""

from __future__ import annotations

import typer

from decoy import __version__
from decoy.ui.banner import render_banner
from decoy.ui.output import OutputMode, emit_json, setup_output


_INFO_EPILOG = """\
Examples:

  decoy info
    Render the branded splash + quick-start hints.

  decoy info --json
    Emit version + counts of bundled topics and templates as JSON.

See also: decoy --help, decoy explain, decoy templates list.
"""


def info(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON record of CLI metadata instead of the banner.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Print the Decoy CLI banner with quick-start hints."""
    state = setup_output(json_, quiet, verbose)

    if state.mode is OutputMode.json:
        from decoy.cli.explain import topic_names
        from decoy.templates import template_names

        emit_json(
            state,
            {
                "command": "info",
                "status": "ok",
                "version": __version__,
                "topics": topic_names(),
                "templates": template_names(),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    render_banner(state)


INFO_EPILOG = _INFO_EPILOG
