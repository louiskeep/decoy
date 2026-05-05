"""`decoy validate` -- check whether a YAML pipeline config is well-formed."""

from pathlib import Path

import typer

from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success


_VALIDATE_EPILOG = """\
Examples:

  decoy validate pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate pipeline.yaml --json
    Emit a JSON status object for scripting.

  decoy validate pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

See also: decoy run.
"""


def validate(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config to validate.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout. Errors still go to stderr.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr; exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Validate a decoy pipeline config without running it.

    Use this in CI or before a long run to fail fast on a bad YAML. Exits 0
    on a well-formed config, 1 on a parse / schema error.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    from decoy_engine import validate_config
    from decoy_engine.exceptions import ConfigError, PipelineValidationError

    try:
        validate_config(config_str)
    except (PipelineValidationError, ConfigError) as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "validate",
                    "status": "error",
                    "config": config_str,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"Invalid config: {exc}")
            state.err_console.print(" ", hint("hint:"), "see `decoy validate --help` for the expected schema.")
        raise typer.Exit(code=1)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {"command": "validate", "status": "ok", "config": config_str},
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(config_str))


VALIDATE_EPILOG = _VALIDATE_EPILOG
