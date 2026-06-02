"""`decoy validate` -- check whether a YAML pipeline config is well-formed.

CLI.2 commit 1 (2026-06-02): rewired against the V2 choke point. Pre-fix the
module imported `validate_graph` (deleted under S22) from `decoy_engine`
and `ConfigError` + `PipelineValidationError` from `decoy_engine.exceptions`
(wrong module; the engine path is `decoy_engine.errors`, exported at the
top-level). Both broke import at runtime. The `_is_graph_yaml` helper +
its branch handled a V1-only `mode: graph` value the V2 schema rejects
at the model layer; deleted.

The V2 choke point is `decoy_engine.PipelineConfig.model_validate(dict)`.
Validates as a single typed step; the cli-product-flow.md doc names it
as the validation contract (line 139).
"""

from pathlib import Path

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_USAGE
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

    from decoy_engine import ConfigError, PipelineConfig, PipelineValidationError
    from pydantic import ValidationError

    def _emit_error(message: str) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "validate",
                    "status": "error",
                    "config": config_str,
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"Invalid config: {message}")
            state.err_console.print(" ", hint("hint:"), "see `decoy validate --help` for the expected schema.")

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(f"YAML parse error: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    if raw is None:
        # CLI QA fix (2026-06-02, F9): an empty YAML file gives raw=None;
        # the type-error branch below reports the unhelpful
        # "must be a YAML mapping, not NoneType". Give the operator a
        # clear "file is empty" message instead.
        _emit_error("Pipeline YAML is empty.")
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        _emit_error(
            f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        PipelineConfig.model_validate(raw)
    except (ValidationError, PipelineValidationError, ConfigError) as exc:
        _emit_error(str(exc))
        raise typer.Exit(code=EXIT_USAGE)

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
