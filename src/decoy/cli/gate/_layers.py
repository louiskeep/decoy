"""The pre-run gate: config, compile and preflight layers behind one entry.

`decoy validate`, `decoy ci check` and (next part) `decoy run` all call
`run_gate_on_config`, so a refusal reads the same on every route. Moved from
`cli/validate.py` (docs/plans/2026-11-06-validate-always.md, P1); the layer bodies are
the same code, plus the changes the plan lists: `GateFinding.extra`, `GateResult.checks_run`
and `.config`, the route rule, the unique-column warning and the target-overwrite
advisory living in the config layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml as _yaml

from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_OK, EXIT_USAGE, EXIT_WARNINGS

# Prefix of the capacity finding on the CHUNKED route, where it is advisory.
_CHUNKED_CAPACITY_NOTE = (
    "ADVISORY (--chunked never takes the out-of-core FK route this check prices, so the "
    "job is not refused) -- "
)


class GateRoute(Enum):
    """How the caller will execute the job; a fact the caller knows, not a user flag.

    CHUNKED never takes the out-of-core FK route that the capacity check prices, so a
    capacity refusal is advisory there.
    """

    PLAIN = "plain"
    CHUNKED = "chunked"


@dataclass
class GateFinding:
    """One finding in the aggregate gate report, tagged by its layer.

    layer    in {config, compile, preflight}
    severity in {error, warning}  (a passing check contributes no finding)
    """

    layer: str
    severity: str
    code: str
    message: str
    location: str | None = None
    # The dotted config path the engine attached, even where the direct command has never
    # surfaced it as `location`. Read by `decoy ci` only; no existing output renders it.
    logical_path: str | None = None
    # The optional extra an absent dependency needs ("ner"), so `decoy run --json` can keep
    # `error_kind: "missing_extra"`.
    extra: str | None = None


@dataclass(frozen=True)
class GateResult:
    """The side-effect-free outcome of the pre-run gate (no rendering, no exit).

    `decoy validate CONFIG` renders it; `decoy ci check` consumes the same value, so the
    CI wrapper cannot drift from the direct command. New fields go last, with defaults.
    """

    findings: list[GateFinding]
    ran_layers: frozenset[str]
    capacity_insufficient: bool
    # Names of the profile-free checks the config layer ran (empty when it failed).
    checks_run: tuple[str, ...] = ()
    # `PipelineConfig.model_validate(raw).model_dump()`, set only when the config layer passed.
    config: dict[str, Any] | None = None


def _plan_error_fields(error: Exception) -> tuple[str, str, str | None]:
    """(code, message, extra) for a `PlanCompileError`; `extra` is set for a missing extra."""
    from decoy.cli.extras import plan_compile_error_fields, translate_ner_unavailable

    code, message = plan_compile_error_fields(error)
    translated = translate_ner_unavailable(error)
    return code, message, (translated.extra if translated is not None else None)


def parse_pipeline_yaml(
    config_path: Path, source_text: str | None = None
) -> tuple[Any, list[GateFinding]]:
    """Parse the pipeline YAML. Syntax only: `raw` comes back unchanged, including `None`,
    lists and scalars, so the gate (not the parser) emits `yaml.empty` / `yaml.not_mapping`.

    On a syntax error returns `(None, [yaml.parse_error])`.
    """
    try:
        text = source_text if source_text is not None else config_path.read_text(encoding="utf-8")
        return _yaml.safe_load(text), []
    except _yaml.YAMLError as exc:
        return None, [GateFinding("config", "error", "yaml.parse_error", sanitize_yaml_error(exc))]


def _findings_from_checks(acc: Any, layer: str) -> list[GateFinding]:
    """Map a preflight accumulator to findings: a `fail` is an error, a `warn` a warning."""
    findings: list[GateFinding] = []
    for c in acc.checks:
        if c.status == "pass":
            continue
        severity = "error" if c.status == "fail" else "warning"
        findings.append(GateFinding(layer, severity, c.code or c.name, c.message, c.location))
    return findings


def _run_config_base(
    raw: Any, config_path: Path
) -> tuple[dict[str, Any] | None, tuple[str, ...], list[GateFinding]]:
    """The config layer: the empty and non-mapping refusals, schema validation, the
    profile-free plan-compile checks, the target-overwrite advisory and the target format
    contradictions (`target_format_issues`, the same rule `decoy run` refuses on).

    `run_config_only_checks` is called here EXACTLY ONCE for the whole gate (F5 dedup).
    Returns `(config, checks_run, findings)`; `config` is None when the layer failed, so the
    caller short-circuits (compile and preflight both need a valid config).
    """
    import decoy_engine
    from decoy_engine import ConfigError, PipelineValidationError, parse_pipeline_config
    from decoy_engine.config import PipelineConfigError
    from decoy_engine.plan import PlanCompileError

    if raw is None:
        return None, (), [GateFinding("config", "error", "yaml.empty", "Pipeline YAML is empty.")]

    if not isinstance(raw, dict):
        return (
            None,
            (),
            [
                GateFinding(
                    "config",
                    "error",
                    "yaml.not_mapping",
                    f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.",
                )
            ],
        )

    try:
        validated = parse_pipeline_config(raw).model_dump()
    except PipelineConfigError as exc:
        findings: list[GateFinding] = [
            GateFinding("config", "error", p.code, p.text, p.location or None) for p in exc.problems
        ]
        return None, (), findings
    except (PipelineValidationError, ConfigError) as exc:
        return (
            None,
            (),
            [
                GateFinding(
                    "config",
                    "error",
                    "pipeline.validation_error",
                    str(exc),
                    logical_path=getattr(exc, "path", None),
                )
            ],
        )

    # Looked up on the module (not a `from ... import` binding) so a test can
    # spy the single call via `decoy_engine.run_config_only_checks`.
    try:
        checks_run = decoy_engine.run_config_only_checks(raw, base_dir=config_path.parent)
    except PlanCompileError as exc:
        err_code, message, extra = _plan_error_fields(exc)
        finding = GateFinding(
            "config", "error", err_code, message, logical_path=exc.path or None, extra=extra
        )
        return None, (), [finding]

    from decoy.cli.io import target_format_issues
    from decoy.cli.preflight import _check_target_overwrite, _PreflightAccumulator

    advisory = _PreflightAccumulator()
    _check_target_overwrite(raw, advisory, config_path.parent)
    findings = _findings_from_checks(advisory, "config")
    # The route is unknown here, so only the route-free contradictions (chunked=False).
    findings.extend(
        GateFinding("config", "error", i.code, i.message, location=f"targets.{i.table}.format")
        for i in target_format_issues(raw, chunked=False)
    )
    return validated, tuple(checks_run), findings


def _run_compile_layer(raw: dict[str, Any], config_dir: Path) -> list[GateFinding]:
    """The compile layer: a no-profile compile and its plan-compile checks,
    composed from the same helpers `validate compile --no-profile` uses (the
    unique-cardinality detector, the empty sentinel profile, `compile_plan`,
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

    findings: list[GateFinding] = []

    # A `cardinality_mode: unique` column needs profile data for the pool-capacity
    # pre-flight, which a no-profile compile cannot run, and a profiled run accepts it. So
    # the aggregate gate skips the compile for it with a warning (owner Q1);
    # `validate compile --no-profile` keeps its error.
    unique_column_path = find_first_unique_column_path(raw)
    if unique_column_path is not None:
        findings.append(
            GateFinding(
                "compile",
                "warning",
                "compile.needs_profile",
                "Compile check skipped: cardinality_mode: unique needs profile data "
                f"(column: {unique_column_path}). Run `decoy validate compile CONFIG "
                "--profile <profile.json>` to check it.",
                unique_column_path,
            )
        )
        return findings

    try:
        # Inside the try: an unequal composite relationship raises `ValueError` here.
        profile = empty_profile_for_no_profile(raw, engine_version)
        plan = compile_plan(
            raw,
            profile,
            decoy_engine_version=engine_version,
            no_profile=True,
            base_dir=config_dir,
        )
    except PlanCompileError as exc:
        err_code, message, extra = _plan_error_fields(exc)
        findings.append(
            GateFinding(
                "compile",
                "error",
                err_code,
                message,
                location=exc.path or None,
                logical_path=exc.path or None,
                extra=extra,
            )
        )
        return findings
    except Exception as exc:  # mirrors `compile`'s own broad compile-error catch
        findings.append(GateFinding("compile", "error", "compile_error", str(exc)))
        return findings

    for w in plan.plan_compile.warnings:
        findings.append(GateFinding("compile", "warning", "compile_warning", w))
    return findings


def _run_preflight_layer(
    raw: dict[str, Any],
    config: Path,
    route: GateRoute,
    compile_errors: frozenset[tuple[str, str | None]] = frozenset(),
) -> tuple[list[GateFinding], bool]:
    """The preflight layer: source/file readiness, out-of-core-FK capacity, and native
    companion/eligibility -- the check functions `validate preflight` runs, reused as-is
    (the target-overwrite advisory lives in the config layer).

    Returns `(findings, capacity_insufficient)`. The capacity fan-in impossibility sets
    `capacity_insufficient` (the EXIT_CAPACITY precedence), except on the CHUNKED route,
    which never takes the route that check prices: there it is a warning.

    A `capacity.plan_uncompilable` FAIL whose (code, location) is in `compile_errors` repeats
    an error the compile layer already reports, so it becomes a not-checked warning. Matching
    the location too keeps a same-code failure at another config path.
    """
    from decoy.cli.preflight import (
        CAPACITY_CHECK,
        PLAN_UNCOMPILABLE_CHECK,
        _check_capacity,
        _check_native,
        _check_source_files,
        _PreflightAccumulator,
    )

    acc = _PreflightAccumulator()
    _check_source_files(raw, config.parent, acc)
    _check_capacity(raw, config, acc)
    _check_native(raw, acc)

    if route is GateRoute.CHUNKED:
        for c in acc.checks:
            if c.name == CAPACITY_CHECK and c.status == "fail":
                c.status = "warn"
                c.message = _CHUNKED_CAPACITY_NOTE + c.message.removeprefix("INSUFFICIENT -- ")
        acc.capacity_insufficient = False
    for c in acc.checks:
        if (
            c.name == PLAN_UNCOMPILABLE_CHECK
            and c.status == "fail"
            and (c.code, c.location or None) in compile_errors
        ):
            c.status = "warn"
            c.code = None
            c.message = "Capacity not checked: the plan does not compile (see the compile error)."
    return _findings_from_checks(acc, "preflight"), acc.capacity_insufficient


def run_gate_on_config(
    raw: Any, config_path: Path, route: GateRoute = GateRoute.PLAIN
) -> GateResult:
    """Config + compile + preflight on an already-parsed YAML value, short-circuiting after a
    failed config layer. `config_path` is used only for its directory."""
    config, checks_run, config_findings = _run_config_base(raw, config_path)
    if config is None:
        return GateResult(config_findings, frozenset({"config"}), False)
    compile_findings = _run_compile_layer(raw, config_path.parent)
    compile_errors = frozenset(
        (f.code, f.location) for f in compile_findings if f.severity == "error"
    )
    preflight_findings, capacity_insufficient = _run_preflight_layer(
        raw, config_path, route, compile_errors
    )
    return GateResult(
        config_findings + compile_findings + preflight_findings,
        frozenset({"config", "compile", "preflight"}),
        capacity_insufficient,
        checks_run,
        config,
    )


def run_config_gate(config: Path, source_text: str | None = None) -> GateResult:
    """Config layer only (YAML + schema + profile-free plan-compile checks)."""
    raw, parse_findings = parse_pipeline_yaml(config, source_text)
    if parse_findings:
        return GateResult(parse_findings, frozenset({"config"}), False)
    validated, checks_run, findings = _run_config_base(raw, config)
    return GateResult(findings, frozenset({"config"}), False, checks_run, validated)


def run_gate(config: Path, source_text: str | None = None) -> GateResult:
    """Config + compile + preflight, short-circuiting after a failed config layer."""
    raw, parse_findings = parse_pipeline_yaml(config, source_text)
    if parse_findings:
        return GateResult(parse_findings, frozenset({"config"}), False)
    return run_gate_on_config(raw, config)


def gate_exit_code(result: GateResult, fail_on_warning: bool) -> int:
    """Exit-code precedence (highest first): capacity, any error, blocking warning, ok."""
    if result.capacity_insufficient:
        # A hard capacity FAIL always exits EXIT_CAPACITY, outranking a co-occurring
        # compile failure (both appear in the report).
        return EXIT_CAPACITY
    if any(f.severity == "error" for f in result.findings):
        return EXIT_USAGE
    if fail_on_warning and any(f.severity == "warning" for f in result.findings):
        return EXIT_WARNINGS
    return EXIT_OK
