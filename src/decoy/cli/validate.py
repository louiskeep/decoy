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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
import yaml as _yaml

from decoy.cli._default_group import make_default_group
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_USAGE, EXIT_WARNINGS
from decoy.ui.output import OutputMode, emit_json, setup_output
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
# Message container (validate config)
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
                message=(f"Output target already exists and would be overwritten: {out_path_str}"),
                location=f"targets.{table_name}.path",
            )


# ---------------------------------------------------------------------------
# `decoy validate config`
# ---------------------------------------------------------------------------


def config(
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
            message=(f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."),
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
        # Rewrite ner_spacy_not_installed to decoy-cli's own [ner] extra;
        # see plan_compile_error_fields's docstring for why every
        # PlanCompileError display site goes through it.
        from decoy.cli.extras import plan_compile_error_fields

        code, message = plan_compile_error_fields(exc)
        acc.add_error(code=code, message=message)
        _emit_result(state, acc, config_str, checks_run=None, fail_on_warning=fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 4: CLI-level advisory checks (no profile needed) -------------
    _check_target_overwrite(raw, acc)

    # -- Step 5: Emit result -----------------------------------------------
    _emit_result(state, acc, config_str, checks_run=checks_run, fail_on_warning=fail_on_warning)

    if fail_on_warning and acc.has_warnings:
        raise typer.Exit(code=EXIT_WARNINGS)


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
        # markup=False: first_error.message is arbitrary text, not authored UI
        # copy -- a missing-extra install line legitimately contains `[ner]`
        # / `[cloud]`, which Rich's markup parser silently drops as an
        # unrecognized tag without markup=False (matches the run.py fix).
        state.err_console.print(
            error("error:"),
            f"Invalid config: {first_error.code}: {first_error.message}",
            markup=False,
        )
        state.err_console.print(
            " ", hint("hint:"), "see `decoy validate config --help` for the expected schema."
        )
        return

    # Success path: show warnings then OK.
    for msg in acc.messages:
        if msg.severity == "warning":
            loc_hint = f" ({msg.location})" if msg.location else ""
            # markup=False: same reason as the error print above; a warning
            # message can quote a user path or other bracketed text.
            state.err_console.print(warn("warning:"), msg.message + loc_hint, markup=False)

    state.console.print(success("OK"), code(config_str))


# ---------------------------------------------------------------------------
# `decoy validate CONFIG` -- the default pre-run gate (config + compile + preflight)
# ---------------------------------------------------------------------------


@dataclass
class _GateFinding:
    """One finding in the aggregate gate report, tagged by its layer.

    layer    in {config, compile, preflight}
    severity in {error, warning}  (a passing check contributes no finding)
    """

    layer: str
    severity: str
    code: str
    message: str
    location: str | None = None


# Canonical layer order for the grouped human report.
_GATE_LAYERS: tuple[tuple[str, str], ...] = (
    ("config", "Config"),
    ("compile", "Compile"),
    ("preflight", "Preflight"),
)


def _run_config_base(config: Path) -> tuple[dict[str, Any] | None, list[_GateFinding]]:
    """The shared config layer: YAML parse + schema validate + the profile-free
    plan-compile checks, composed exactly as `validate config` composes them.

    `run_config_only_checks` is called here EXACTLY ONCE for the whole gate
    (F5 dedup): compile_plan re-validates a superset of these checks internally
    on the success path, but the engine's `run_config_only_checks` entrypoint
    itself fires only on this call.

    Returns `(raw, [])` when the config is valid, or `(None, findings)` with the
    config-layer error(s) when it fails to parse / schema-validate / pass the
    config-only checks. A None result means compile/preflight cannot run (they
    both need a valid config), so the caller short-circuits with EXIT_USAGE.
    """
    import decoy_engine
    from decoy_engine import ConfigError, PipelineConfig, PipelineValidationError
    from decoy_engine.plan import PlanCompileError
    from pydantic import ValidationError

    findings: list[_GateFinding] = []

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        findings.append(_GateFinding("config", "error", "yaml.parse_error", f"YAML parse error: {exc}"))
        return None, findings

    if raw is None:
        findings.append(_GateFinding("config", "error", "yaml.empty", "Pipeline YAML is empty."))
        return None, findings

    if not isinstance(raw, dict):
        findings.append(
            _GateFinding(
                "config",
                "error",
                "yaml.not_mapping",
                f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.",
            )
        )
        return None, findings

    try:
        PipelineConfig.model_validate(raw)
    except ValidationError as exc:
        for e in exc.errors():
            loc_parts = [str(p) for p in e.get("loc", ())]
            location = ".".join(loc_parts) if loc_parts else None
            findings.append(
                _GateFinding(
                    "config", "error", e.get("type", "validation_error"), e.get("msg", str(e)), location
                )
            )
        return None, findings
    except (PipelineValidationError, ConfigError) as exc:
        findings.append(_GateFinding("config", "error", "pipeline.validation_error", str(exc)))
        return None, findings

    # Looked up on the module (not a `from ... import` binding) so a test can
    # spy the single call via `decoy_engine.run_config_only_checks`.
    try:
        decoy_engine.run_config_only_checks(raw)
    except PlanCompileError as exc:
        from decoy.cli.extras import plan_compile_error_fields

        err_code, message = plan_compile_error_fields(exc)
        findings.append(_GateFinding("config", "error", err_code, message))
        return None, findings

    return raw, findings


def _run_compile_layer(raw: dict[str, Any]) -> list[_GateFinding]:
    """The compile layer: a no-profile compile and its plan-compile checks,
    composed from the same helpers `validate compile --no-profile` uses (the
    H2 unique-cardinality guard, the empty sentinel profile, `compile_plan`,
    and the H1 checks-skipped attachment). No check logic is reimplemented.

    Returns compile-layer findings (an error on a compile failure; warnings for
    any plan-compile warnings). Never raises on a compile error -- the gate runs
    all layers and aggregates rather than short-circuiting here.
    """
    from decoy_engine import __version__ as engine_version
    from decoy_engine.plan import PlanCompileError, compile_plan

    from decoy.cli.plan import (
        empty_profile_for_no_profile,
        find_first_unique_column_path,
    )

    findings: list[_GateFinding] = []

    # H2 guard (reused from the `compile` command): --no-profile cannot run the
    # pool-capacity pre-flight, so a cardinality_mode: unique column is refused.
    unique_column_path = find_first_unique_column_path(raw)
    if unique_column_path is not None:
        findings.append(
            _GateFinding(
                "compile",
                "error",
                "no_profile_unique_incompatible",
                "--no-profile is incompatible with cardinality_mode: unique "
                f"(offending column: {unique_column_path}). The basic_uniqueness_pre_flight "
                "check requires profile data; run `decoy validate compile CONFIG "
                "--profile <profile.json>`, or remove the unique cardinality_mode.",
                unique_column_path,
            )
        )
        return findings

    profile = empty_profile_for_no_profile(raw, engine_version)
    try:
        plan = compile_plan(raw, profile, decoy_engine_version=engine_version, no_profile=True)
    except PlanCompileError as exc:
        from decoy.cli.extras import plan_compile_error_fields

        err_code, message = plan_compile_error_fields(exc)
        findings.append(
            _GateFinding("compile", "error", err_code, message, location=exc.path or None)
        )
        return findings
    except Exception as exc:  # mirrors `compile`'s own broad compile-error catch
        findings.append(_GateFinding("compile", "error", "compile_error", str(exc)))
        return findings

    for w in plan.plan_compile.warnings:
        findings.append(_GateFinding("compile", "warning", "compile_warning", w))
    return findings


def _run_preflight_layer(raw: dict[str, Any], config: Path) -> tuple[list[_GateFinding], bool]:
    """The preflight layer: source/file readiness, target-overwrite advisory,
    out-of-core-FK capacity, and native companion/eligibility -- the exact check
    functions `validate preflight` runs for its steps 4-7, reused as-is (steps
    1-3 are the shared config base, already run once).

    Returns `(findings, capacity_insufficient)`: passing checks contribute no
    finding; a `fail` maps to an error and a `warn` to a warning. The capacity
    fan-in impossibility sets `capacity_insufficient`, which the caller uses for
    the EXIT_CAPACITY precedence.
    """
    from decoy.cli.preflight import (
        _check_capacity,
        _check_native,
        _check_source_files,
        _check_target_overwrite,
        _PreflightAccumulator,
    )

    acc = _PreflightAccumulator()
    _check_source_files(raw, config.parent, acc)
    _check_target_overwrite(raw, acc)
    _check_capacity(raw, config, acc)
    _check_native(raw, acc)

    findings: list[_GateFinding] = []
    for c in acc.checks:
        if c.status == "pass":
            continue
        severity = "error" if c.status == "fail" else "warning"
        findings.append(
            _GateFinding("preflight", severity, c.code or c.name, c.message, c.location)
        )
    return findings, acc.capacity_insufficient


def _gate(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config to run the whole pre-run gate against.",
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
    and exits by precedence: a capacity fan-in refusal -> EXIT_CAPACITY (it
    outranks a co-occurring compile failure); any other failure -> EXIT_USAGE;
    warnings with --fail-on-warning -> EXIT_WARNINGS; otherwise 0.

    The subcommands (`config`, `compile`, `preflight`) run a single layer
    each and keep their own output and exit semantics.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    raw, config_findings = _run_config_base(config)
    if raw is None:
        # Config base failed: compile/preflight cannot run. Short-circuit.
        _emit_gate(state, config_findings, config_str, fail_on_warning, ran_layers={"config"})
        raise typer.Exit(code=EXIT_USAGE)

    compile_findings = _run_compile_layer(raw)
    preflight_findings, capacity_insufficient = _run_preflight_layer(raw, config)
    findings = config_findings + compile_findings + preflight_findings

    _emit_gate(
        state,
        findings,
        config_str,
        fail_on_warning,
        ran_layers={"config", "compile", "preflight"},
    )

    # Exit-code precedence (highest first).
    if capacity_insufficient:
        # A hard capacity FAIL always exits EXIT_CAPACITY, outranking a
        # co-occurring compile failure (both appear in the report).
        raise typer.Exit(code=EXIT_CAPACITY)
    if any(f.severity == "error" for f in findings):
        raise typer.Exit(code=EXIT_USAGE)
    if fail_on_warning and any(f.severity == "warning" for f in findings):
        raise typer.Exit(code=EXIT_WARNINGS)
    # else EXIT_OK (implicit clean return)


def _emit_gate(
    state: Any,
    findings: list[_GateFinding],
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
        state.err_console.print(
            warn("warning:"), "warnings present and --fail-on-warning is set."
        )


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
