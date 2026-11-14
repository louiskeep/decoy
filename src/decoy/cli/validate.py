"""`decoy validate` -- the pre-run validation gate (config / compile / preflight).

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

Sprint 5 (BF1, 2026-07-04): `validate` is promoted from a flat command to
a Typer group so sibling subcommands can sit beside the original check. Per
the CLI's CLAUDE.md ("Pre-GA = hard delete"), the old `decoy validate <cfg>`
invocation is renamed to `decoy validate config <cfg>`; the `config`
subcommand's body is the pre-promotion `validate()` function, moved unchanged
(same envelope shape, same exit-code contract).

S4b (CLI redesign): `validate` is now purely PRE-RUN -- it owns
`config` / `compile` / `preflight` only. The former post-run distribution
fidelity check relocated to `decoy report fidelity`
(`decoy.cli.report._fidelity`), beside the other post-run verbs.
"""

from __future__ import annotations

from typing import Any

import typer

from decoy._config_file import config_refusal
from decoy.cli._default_group import make_default_group
from decoy.cli.exit_codes import EXIT_OK, exit_code_for
from decoy.cli.gate import GateFinding, gate_exit_code, run_config_gate, run_gate
from decoy.cli.io import pipeline_argument, resolve_pipeline
from decoy.ui.output import OutputMode, emit_error, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, success, warn

_VALIDATE_EPILOG = """\
Examples:

  decoy validate pipeline.yaml
    Run the whole pre-run gate (config + compile + preflight): one report
    grouped by layer, one aggregated exit code.

  decoy validate config pipeline.yaml
    Schema + config-only checks (fast, no source read).

  decoy validate compile pipeline.yaml --explain
    Compile the plan, run plan-compile checks, explain per-column decisions.

  decoy validate preflight pipeline.yaml
    Source / file / schema readiness + capacity estimate + native probe.

See also: decoy run, decoy fit, decoy report fidelity.
"""

validate_app = typer.Typer(
    name="validate",
    cls=make_default_group("_gate"),
    help=(
        "Pre-run validation gate. `decoy validate CONFIG` runs the whole gate "
        "(config + compile + preflight) and emits one report + one exit code. "
        "Subcommands run a single layer: schema + config checks (`config`), plan "
        "compilation + checks (`compile`), and source/capacity readiness "
        "(`preflight`). Post-run fidelity checks moved to `decoy report fidelity`."
    ),
    epilog=_VALIDATE_EPILOG,
    no_args_is_help=True,
)

_CONFIG_EPILOG = """\
Examples:

  decoy validate config pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate config pipeline.yaml --json
    Emit a structured JSON result (multi-message) for scripting.

  decoy validate config pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

  decoy validate config pipeline.yaml --fail-on-warning
    Exit non-zero if any advisory warning fires (e.g. output target exists).

See also: decoy run, decoy report fidelity.
"""


# ---------------------------------------------------------------------------
# `decoy validate config`
# ---------------------------------------------------------------------------


def config(
    config: str = pipeline_argument(help="Path or name of the YAML pipeline config to validate."),
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
    config_path = resolve_pipeline(config, state, "validate").yaml

    try:
        result = run_config_gate(config_path)
    except OSError as exc:
        emit_error(state, "validate config", **config_refusal(exc), context={"config": str(config)})
        raise typer.Exit(code=exit_code_for(exc))
    _emit_result(state, result.findings, str(config), result.checks_run)
    code = gate_exit_code(result, fail_on_warning)
    if code != EXIT_OK:
        raise typer.Exit(code=code)


def _emit_result(
    state: Any,
    findings: list[GateFinding],
    config_str: str,
    checks_run: tuple[str, ...],
) -> None:
    """Render the config-layer result of `validate config` to the chosen output mode."""
    errors = [f for f in findings if f.severity == "error"]
    messages = [
        {
            "severity": f.severity,
            "code": f.code,
            "message": f.message,
            **({"location": f.location} if f.location is not None else {}),
        }
        for f in findings
    ]
    if state.mode is OutputMode.json:
        if errors:
            # Backward-compat: keep top-level "error" for the first error message.
            first_error = errors[0]
            envelope: dict[str, Any] = {
                "command": "validate",
                "status": "error",
                "config": config_str,
                "error": first_error.message,
                "messages": messages,
            }
        else:
            status = "ok"
            envelope = {
                "command": "validate",
                "status": status,
                "config": config_str,
                "messages": messages,
            }
            envelope["checks_run"] = list(checks_run)
        emit_json(state, envelope)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable output.
    if errors:
        first_error = errors[0]
        # Include the error code so plan-compile codes (non_poolable_provider_with_pool_backend,
        # unknown_provider, etc.) remain visible in human output -- matches old behavior
        # where PlanCompileError emitted "{exc.code}: {exc.message}".
        # markup=False: first_error.message is arbitrary text, not authored UI
        # copy -- a missing-extra install line legitimately contains `[ner]`
        # / `[cloud]`, which Rich's markup parser silently drops as an
        # unrecognized tag without markup=False (matches the run.py fix).
        state.err_console.print(
            error("error:"),
            f"Invalid config: {first_error.code}: {first_error.message}"
            + (f" ({first_error.location})" if first_error.location else ""),
            markup=False,
        )
        state.err_console.print(
            " ", hint("hint:"), "see `decoy validate config --help` for the expected schema."
        )
        return

    # Success path: show warnings then OK.
    for f in findings:
        if f.severity == "warning":
            loc_hint = f" ({f.location})" if f.location else ""
            # markup=False: same reason as the error print above; a warning
            # message can quote a user path or other bracketed text.
            state.err_console.print(warn("warning:"), f.message + loc_hint, markup=False)

    state.console.print(success("OK"), code(config_str))


# ---------------------------------------------------------------------------
# `decoy validate CONFIG` -- the default pre-run gate (config + compile + preflight)
# ---------------------------------------------------------------------------


# Canonical layer order for the grouped human report.
_GATE_LAYERS: tuple[tuple[str, str], ...] = (
    ("config", "Config"),
    ("compile", "Compile"),
    ("preflight", "Preflight"),
)


def _gate(
    config: str = pipeline_argument(
        help="Path or name of the YAML pipeline config to run the whole pre-run gate against.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit one aggregate JSON envelope on stdout (command/status/messages).",
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
        help="Exit non-zero (EXIT_WARNINGS) when any advisory warning fires across the gate.",
    ),
) -> None:
    """Run the whole pre-run gate: config + compile + preflight in one pass.

    This is `decoy validate CONFIG` with no subcommand. It runs the shared
    config base once (YAML parse + schema + the profile-free plan-compile
    checks); if that fails it reports the error and exits EXIT_USAGE without
    running compile/preflight. Otherwise it runs BOTH the compile layer and the
    preflight layer, aggregates every finding into one report grouped by layer,
    and exits by precedence: a capacity refusal (fan-in, out-of-core memory or generated
    output over the memory budget) -> EXIT_CAPACITY (it
    outranks a co-occurring compile failure); any other failure -> EXIT_USAGE;
    warnings with --fail-on-warning -> EXIT_WARNINGS; otherwise 0.

    The subcommands (`config`, `compile`, `preflight`) run a single layer
    each and keep their own output and exit semantics.
    """
    state = setup_output(json_, quiet, verbose)
    config_path = resolve_pipeline(config, state, "validate").yaml
    config_str = str(config)

    try:
        result = run_gate(config_path)
    except OSError as exc:
        emit_error(state, "validate", **config_refusal(exc), context={"config": config_str})
        raise typer.Exit(code=exit_code_for(exc))
    _emit_gate(
        state,
        result.findings,
        config_str,
        fail_on_warning,
        ran_layers=set(result.ran_layers),
    )
    code = gate_exit_code(result, fail_on_warning)
    if code != EXIT_OK:
        raise typer.Exit(code=code)


def _emit_gate(
    state: Any,
    findings: list[GateFinding],
    config_str: str,
    fail_on_warning: bool,
    ran_layers: set[str],
) -> None:
    """Render the aggregate gate result: a grouped human report, or ONE JSON
    envelope `{command, status, config, messages:[{layer, severity, code,
    message, location}]}`.

    Coarser by design than `validate preflight --json`: no structured
    capacity/native_companion blocks, just the flat `messages` list.
    """
    has_error = any(f.severity == "error" for f in findings)
    has_warning = any(f.severity == "warning" for f in findings)

    if state.mode is OutputMode.json:
        if has_error:
            status = "error"
        elif has_warning and fail_on_warning:
            status = "warn"
        else:
            status = "ok"
        envelope: dict[str, Any] = {
            "command": "validate",
            "status": status,
            "config": config_str,
            "messages": [
                {
                    "layer": f.layer,
                    "severity": f.severity,
                    "code": f.code,
                    "message": f.message,
                    "location": f.location,
                }
                for f in findings
            ],
        }
        emit_json(state, envelope)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable: group by layer, in canonical order. Only layers that
    # actually ran are shown (so a config short-circuit does not claim
    # compile/preflight "passed" when they never ran).
    for key, label in _GATE_LAYERS:
        if key not in ran_layers:
            continue
        layer_findings = [f for f in findings if f.layer == key]
        errs = [f for f in layer_findings if f.severity == "error"]
        warns = [f for f in layer_findings if f.severity == "warning"]
        if not errs and not warns:
            state.console.print(success("OK"), f"{label}: passed")
            continue
        state.console.print(accent(f"{label}:"))
        # markup=False throughout: a finding message is not authored markup --
        # it can carry a user path or an install hint like `decoy-cli[ner]`.
        for f in errs:
            loc_hint = f" ({f.location})" if f.location else ""
            state.err_console.print(error("  fail:"), f.message + loc_hint, markup=False)
        for f in warns:
            loc_hint = f" ({f.location})" if f.location else ""
            state.err_console.print(warn("  warning:"), f.message + loc_hint, markup=False)

    if has_error:
        state.err_console.print(
            error("FAIL"), code(config_str), hint("- fix the errors above, then rerun.")
        )
        return

    state.console.print(success("OK"), code(config_str))
    if has_warning and fail_on_warning:
        state.err_console.print(warn("warning:"), "warnings present and --fail-on-warning is set.")


validate_app.command(name="config", epilog=_CONFIG_EPILOG)(config)
# The hidden default command: `decoy validate CONFIG` (no subcommand) routes
# here via `_DefaultCommandGroup`. Hidden so it stays out of help / the
# generated reference / completion, while the group can still dispatch to it.
validate_app.command(name="_gate", hidden=True)(_gate)

# S2: the top-level `compile` and `preflight` commands were re-parented under
# `validate` (and `plan` was folded into `validate compile`). Their bodies
# stay in their own modules; register them here beside config.
from decoy.cli.compile_explain import COMPILE_EPILOG  # noqa: E402
from decoy.cli.compile_explain import compile as _compile_command  # noqa: E402
from decoy.cli.preflight import PREFLIGHT_EPILOG  # noqa: E402
from decoy.cli.preflight import preflight as _preflight_command  # noqa: E402

validate_app.command(name="compile", epilog=COMPILE_EPILOG)(_compile_command)
validate_app.command(name="preflight", epilog=PREFLIGHT_EPILOG)(_preflight_command)

VALIDATE_EPILOG = _VALIDATE_EPILOG

__all__ = ["VALIDATE_EPILOG", "validate_app"]
