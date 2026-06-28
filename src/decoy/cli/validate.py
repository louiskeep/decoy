"""`decoy validate` -- check whether a YAML pipeline config is well-formed.

CLI.2 commit 1 (2026-06-02): rewired against the V2 choke point. Pre-fix the
module imported `validate_graph` (deleted under S22) from `decoy_engine`
and `ConfigError` + `PipelineValidationError` from `decoy_engine.exceptions`
(wrong module; the engine path is `decoy_engine.errors`, exported at the
top-level). Both broke import at runtime. The `_is_graph_yaml` helper +
its branch handled a V1-only `mode: graph` value the V2 schema rejects
at the model layer; deleted.

The V2 choke point is `decoy_engine.PipelineConfig.model_validate(dict)`
followed by `decoy_engine.run_config_only_checks(dict)` (audit H5,
2026-06-12). Schema validation alone green-lit configs that were
guaranteed to crash at `decoy run` (e.g. `strategy: faker` on a
non-poolable provider); the config-only checks are the profile-free
subset of run's plan-compile checks, so validate now rejects exactly
what run would reject without needing source data.

SP-16 (2026-06-28):
- Added `--fail-on-warning`: exits non-zero when any advisory warning is
  present. Enables CI gates that treat warnings as blocking.
- Multi-message JSON output: `--json` now emits a `messages` list with
  ALL validation messages (severity/code/message/location). Previously the
  envelope carried only the first error string. Pydantic ValidationError
  can surface multiple field errors simultaneously; they all appear now.
- CLI-level advisory: warns when a configured output target file already
  exists on disk (overwrite risk). Not an error; blocking only with
  --fail-on-warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_WARN_EXIT = 2  # Exit code for --fail-on-warning when warnings exist

_VALIDATE_EPILOG = """\
Examples:

  decoy validate pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate pipeline.yaml --json
    Emit a structured JSON result (multi-message) for scripting.

  decoy validate pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

  decoy validate pipeline.yaml --fail-on-warning
    Exit non-zero if any advisory warning fires (e.g. output target exists).

See also: decoy run.
"""


# ---------------------------------------------------------------------------
# Message container
# ---------------------------------------------------------------------------


@dataclass
class _ValidationMessage:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.location is not None:
            d["location"] = self.location
        return d


@dataclass
class _ValidationAccumulator:
    messages: list[_ValidationMessage] = field(default_factory=list)

    def add_error(self, code: str, message: str, location: str | None = None) -> None:
        self.messages.append(
            _ValidationMessage(severity="error", code=code, message=message, location=location)
        )

    def add_warning(self, code: str, message: str, location: str | None = None) -> None:
        self.messages.append(
            _ValidationMessage(severity="warning", code=code, message=message, location=location)
        )

    @property
    def has_errors(self) -> bool:
        return any(m.severity == "error" for m in self.messages)

    @property
    def has_warnings(self) -> bool:
        return any(m.severity == "warning" for m in self.messages)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.messages]


# ---------------------------------------------------------------------------
# CLI-level advisory checks (no engine profile needed)
# ---------------------------------------------------------------------------


def _check_target_overwrite(raw: dict[str, Any], acc: _ValidationAccumulator) -> None:
    """Warn when a file target's output path already exists on disk.

    Running the pipeline would silently overwrite the file. Not an error
    (the run succeeds), but a meaningful advisory for CI users who want
    explicit confirmation before clobbering output.
    """
    targets = raw.get("targets") or {}
    if not isinstance(targets, dict):
        return
    for table_name, target in targets.items():
        if not isinstance(target, dict):
            continue
        if target.get("type") not in ("file", None):
            continue
        out_path_str = target.get("path")
        if not out_path_str:
            continue
        out_path = Path(out_path_str)
        if out_path.exists():
            acc.add_warning(
                code="target_file.would_overwrite",
                message=(
                    f"Output target already exists and would be overwritten: {out_path_str}"
                ),
                location=f"targets.{table_name}.path",
            )


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


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
    fail_on_warning: bool = typer.Option(
        False,
        "--fail-on-warning",
        help=(
            "Exit non-zero if any advisory warning fires (e.g. output target exists). "
            "Enables CI gates that treat warnings as blocking."
        ),
    ),
) -> None:
    """Validate a decoy pipeline config without running it.

    Use this in CI or before a long run to fail fast on a bad YAML. Exits 0
    on a well-formed config, 1 on a parse / schema error or a config-level
    plan-compile error (unknown provider, non-poolable provider on the
    faker/pool path, missing deterministic namespace).

    With --fail-on-warning, also exits non-zero when advisory warnings fire
    (e.g. an output file already exists and would be overwritten on run).
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)
    acc = _ValidationAccumulator()

    from decoy_engine import (
        ConfigError,
        PipelineConfig,
        PipelineValidationError,
        run_config_only_checks,
    )
    from decoy_engine.plan import PlanCompileError
    from pydantic import ValidationError

    # -- Step 1: YAML parse ------------------------------------------------
    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        acc.add_error(code="yaml.parse_error", message=f"YAML parse error: {exc}")
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    if raw is None:
        # CLI QA fix (2026-06-02, F9): an empty YAML file gives raw=None.
        acc.add_error(code="yaml.empty", message="Pipeline YAML is empty.")
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        acc.add_error(
            code="yaml.not_mapping",
            message=(
                f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."
            ),
        )
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 2: Schema validation (multi-message from pydantic) -----------
    try:
        PipelineConfig.model_validate(raw)
    except ValidationError as exc:
        # Collect ALL pydantic errors, not just the first.
        for e in exc.errors():
            loc_parts = [str(p) for p in e.get("loc", ())]
            location = ".".join(loc_parts) if loc_parts else None
            acc.add_error(
                code=e.get("type", "validation_error"),
                message=e.get("msg", str(e)),
                location=location,
            )
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)
    except (PipelineValidationError, ConfigError) as exc:
        acc.add_error(code="pipeline.validation_error", message=str(exc))
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 3: Profile-free plan-compile checks --------------------------
    # Audit H5: profile-free plan-compile checks. Strict subset of what
    # `decoy run` enforces; a config rejected here was guaranteed to fail
    # at run; a config accepted here can still fail run's profile-dependent
    # checks (capacity, null-bearing ints).
    try:
        checks_run = run_config_only_checks(raw)
    except PlanCompileError as exc:
        acc.add_error(code=exc.code, message=exc.message)
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 4: CLI-level advisory checks (no profile needed) -------------
    _check_target_overwrite(raw, acc)

    # -- Step 5: Emit result -----------------------------------------------
    _emit_result(state, acc, config_str, checks_run=checks_run, fail_on_warning=fail_on_warning)

    if fail_on_warning and acc.has_warnings:
        raise typer.Exit(code=_WARN_EXIT)


def _emit_result(
    state: Any,
    acc: _ValidationAccumulator,
    config_str: str,
    checks_run: tuple[str, ...] | None,
    fail_on_warning: bool,
) -> None:
    """Render the accumulated validation result to the chosen output mode."""
    if state.mode is OutputMode.json:
        if acc.has_errors:
            # Backward-compat: keep top-level "error" for the first error message.
            first_error = next(m for m in acc.messages if m.severity == "error")
            envelope: dict[str, Any] = {
                "command": "validate",
                "status": "error",
                "config": config_str,
                "error": first_error.message,
                "messages": acc.to_dicts(),
            }
        else:
            status = "ok"
            envelope = {
                "command": "validate",
                "status": status,
                "config": config_str,
                "messages": acc.to_dicts(),
            }
            if checks_run is not None:
                envelope["checks_run"] = list(checks_run)
        emit_json(state, envelope)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable output.
    if acc.has_errors:
        first_error = next(m for m in acc.messages if m.severity == "error")
        # Include the error code so plan-compile codes (non_poolable_provider_with_pool_backend,
        # unknown_provider, etc.) remain visible in human output -- matches old behavior
        # where PlanCompileError emitted "{exc.code}: {exc.message}".
        state.err_console.print(
            error("error:"), f"Invalid config: {first_error.code}: {first_error.message}"
        )
        state.err_console.print(
            " ", hint("hint:"), "see `decoy validate --help` for the expected schema."
        )
        return

    # Success path: show warnings then OK.
    for msg in acc.messages:
        if msg.severity == "warning":
            loc_hint = f" ({msg.location})" if msg.location else ""
            state.err_console.print(warn("warning:"), msg.message + loc_hint)

    state.console.print(success("OK"), code(config_str))


VALIDATE_EPILOG = _VALIDATE_EPILOG
