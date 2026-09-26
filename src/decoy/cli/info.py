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

    companion = _companion_report()

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
                "native_companion": companion,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    render_banner(state)
    _render_companion_report(state, companion)


def _companion_report() -> dict:
    """`native_companion_status()`, reduced to the fields safe to display:
    never `status.cause` (may chain an exception with a path), and
    `abi_actual` sanitized (it comes from the companion's own untrusted
    `abi_version()` call -- see `decoy._native_gate.sanitize_abi`)."""
    from decoy_engine import native_companion_status

    from decoy import _native_gate

    status = native_companion_status()
    return {
        "present": status.present,
        "ok": status.ok,
        "reason": status.reason,
        "abi_expected": status.abi_expected,
        "abi_actual": _native_gate.sanitize_abi(status.abi_actual),
        "version": status.version,
    }


def _render_companion_report(state, companion: dict) -> None:
    from rich.text import Text

    from decoy.ui.theme import hint, success, warn

    label = "native: "
    if companion["ok"]:
        state.console.print(success(label + "present, healthy"), f"(v{companion['version']})")
    elif companion["present"]:
        state.console.print(
            warn(label + f"present but not usable ({companion['reason']})"),
            # Text(): abi_actual is untrusted third-party display text
            # (sanitized, but still not markup-safe -- see sanitize_abi).
            Text(f"-- expected ABI {companion['abi_expected']}, got {companion['abi_actual']!r}"),
        )
    else:
        state.console.print(
            hint(label + "not installed"),
            # Text(): the literal "decoy-cli[native]" extras spec would
            # otherwise be reinterpreted as Rich markup.
            Text("-- install decoy-cli[native] to enable compiled-kernel acceleration."),
        )


INFO_EPILOG = _INFO_EPILOG
