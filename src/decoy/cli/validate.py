"""`decoy validate` -- config schema checks + distribution fidelity checks.

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
a Typer group so `validate distribution` can sit beside the original
check. Per the CLI's CLAUDE.md ("Pre-GA = hard delete"), the old
`decoy validate <cfg>` invocation is renamed to `decoy validate config
<cfg>`; the `config` subcommand's body is the pre-promotion `validate()`
function, moved unchanged (same envelope shape, same exit-code contract).

`validate distribution <source> <output>` is the CLI surface for BF1: it
recomputes distribution fidelity between a pre-mask/pre-generate source
CSV and a post-mask/post-generate output CSV via the engine's
`decoy_engine.quality.compute_quality_report` + `apply_quality_policy`
(report.py:97, policy.py:142) -- the same functions `decoy fit` already
depends on siblings of (fit.py:144). This command computes NO fidelity
metric itself; it is a thin CLI surface over the engine. Recompute (not a
stored-metric read) is the honest path here: the CLI's local evidence
manifest (`decoy evidence show/verify`) records file fingerprints but not
the raw frames, so it cannot supply the data the engine needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_WARN_EXIT = 2  # Exit code for --fail-on-warning when warnings exist

# Grade -> minimum overall_score, mirroring the engine's own grade
# thresholds (decoy_engine.quality.report._GRADE_THRESHOLDS: A >= 0.95,
# B >= 0.85, C >= 0.70, D >= 0.50). The engine maps score -> grade; there
# is no reverse (grade -> score) helper on the public surface, so
# `--min-grade` needs its own copy of the same table to translate into a
# `thresholds.overall.min` policy value. This is a threshold-translation
# convenience, not a new metric: the score and grade themselves still
# come entirely from `compute_quality_report`.
_GRADE_MIN_SCORE: dict[str, float] = {"A": 0.95, "B": 0.85, "C": 0.70, "D": 0.50}

_VALIDATE_EPILOG = """\
Examples:

  decoy validate config pipeline.yaml
    Check a YAML pipeline config before running it.

  decoy validate distribution source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output.

See also: decoy run, decoy fit.
"""

validate_app = typer.Typer(
    name="validate",
    help=(
        "Validate a pipeline config (`config`) or check distribution "
        "fidelity between a source and an output (`distribution`)."
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

See also: decoy run, decoy validate distribution.
"""

_DISTRIBUTION_EPILOG = """\
Examples:

  decoy validate distribution source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output. Report mode (record only): always exits 0.

  decoy validate distribution source.csv output.csv --config pipeline.yaml
    Pass the pipeline config so intentional loss (hash, bucketize, ...)
    is not flagged as accidental drift.

  decoy validate distribution source.csv synthetic.csv --generate
    Row counts are expected to differ (synthetic generation, not masking).

  decoy validate distribution source.csv output.csv --mode fail --min-grade B
    Exit non-zero (EXIT_FINDINGS) when the overall grade falls below B.

  decoy validate distribution source.csv output.csv --joint state,tier --json
    Include a (state, tier) joint fidelity score; emit the full
    quality-report/v1 + policy JSON.

  decoy validate distribution source.csv output.csv --report-out report.json
    Also write the full report + policy verdict to disk.

Exit codes: 0 pass (or warn without --fail-on-warning); 4 EXIT_FINDINGS
when the policy verdict is fail, or warn with --fail-on-warning set;
1 EXIT_USAGE for bad input (missing columns, unreadable CSV, bad flags).

Note: the sibling `validate config --fail-on-warning` exits 2 for its
warnings (config well-formedness), while this command exits 4 for its
warnings (data-fidelity findings). The two subcommands intentionally use
different warning exit codes for their different domains.

See also: decoy validate config, decoy fit, decoy run.
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
                message=(
                    f"Output target already exists and would be overwritten: {out_path_str}"
                ),
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
            " ", hint("hint:"), "see `decoy validate config --help` for the expected schema."
        )
        return

    # Success path: show warnings then OK.
    for msg in acc.messages:
        if msg.severity == "warning":
            loc_hint = f" ({msg.location})" if msg.location else ""
            state.err_console.print(warn("warning:"), msg.message + loc_hint)

    state.console.print(success("OK"), code(config_str))


# ---------------------------------------------------------------------------
# `decoy validate distribution` (BF1)
# ---------------------------------------------------------------------------


def _build_strategy_map(config_dict: dict[str, Any]) -> dict[str, str]:
    """Flatten column -> strategy across every declared table.

    Mirrors the evidence manifest's strategy-summary loop
    (`decoy.cli.evidence.build_manifest`). `validate distribution` checks a
    single source/output CSV pair, not a specific table, so this assumes
    column names are unique across the pipeline's declared tables; a
    multi-table config with a repeated column name lets the last table's
    strategy win. Acceptable for the v1 single source/output scope (D4).
    """
    strategy_map: dict[str, str] = {}
    for table in config_dict.get("tables") or []:
        if not isinstance(table, dict):
            continue
        for col in table.get("columns") or []:
            if isinstance(col, dict) and col.get("name"):
                strategy_map[col["name"]] = col.get("strategy", "")
        for gen_col in table.get("generate_columns") or []:
            if isinstance(gen_col, dict) and gen_col.get("name"):
                strategy_map[gen_col["name"]] = "generate"
    return strategy_map


def distribution(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Pre-mask / pre-generate source CSV (ground truth).",
    ),
    output: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Post-mask / post-generate output CSV to check.",
    ),
    joint: list[str] = typer.Option(
        [],
        "--joint",
        help="Column pair 'a,b' to also score jointly (repeatable).",
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        help=(
            "Output is synthetic generation, not masking: row counts may "
            "legitimately differ (sets expect_row_parity=False). Default "
            "assumes masking (row parity expected)."
        ),
    ),
    pipeline_config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Pipeline YAML naming each column's strategy, so intentional "
            "loss (hash, bucketize, faker, ...) is not flagged as accidental "
            "drift. Without it, per-column policy checks run on defaults only."
        ),
    ),
    policy: Path | None = typer.Option(
        None,
        "--policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "A quality-policy config (YAML or JSON: mode / thresholds / "
            "strategy_expectations) overriding --mode / --min-grade / --min-score."
        ),
    ),
    mode: str = typer.Option(
        "report",
        "--mode",
        help=(
            "report (record only, verdict always pass) | warn (violations "
            "promote verdict to warn) | fail (violations promote verdict to "
            "fail). Ignored when --policy sets its own mode."
        ),
    ),
    min_grade: str | None = typer.Option(
        None,
        "--min-grade",
        help="Shorthand: minimum letter grade (A/B/C/D) the overall score must reach.",
    ),
    min_score: float | None = typer.Option(
        None,
        "--min-score",
        help="Shorthand: minimum overall_score in [0, 1].",
    ),
    fail_on_warning: bool = typer.Option(
        False,
        "--fail-on-warning",
        help="Also exit non-zero (EXIT_FINDINGS) when the policy verdict is 'warn'.",
    ),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Write the full quality-report/v1 + policy JSON to this path.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full quality-report/v1 + policy result as JSON.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Recompute distribution fidelity between a source and an output CSV.

    The engine owns every metric and the letter grade; this command
    computes no fidelity number itself. Reads both CSVs fresh on every
    invocation (pure, repeatable) -- the CLI's local evidence manifest
    records file fingerprints but not the raw frames, so recomputing from
    the two files is the only honest source for this number.

    Exit codes: 0 when the policy verdict is 'pass' (or 'warn' without
    --fail-on-warning); EXIT_FINDINGS (4) when the verdict is 'fail', or
    'warn' with --fail-on-warning set. This mirrors `decoy storm
    integrity`'s exit-code contract -- a data-audit verb that reports
    findings, not a run that crashed -- rather than EXIT_RUNTIME (reserved
    for the CLI/engine blowing up unexpectedly).
    """
    state = setup_output(json_, quiet, verbose)
    source_str = str(source)
    output_str = str(output)

    def _emit_error(message: str) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "validate distribution",
                    "status": "error",
                    "source": source_str,
                    "output": output_str,
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            _emit_error(f"--joint expects 'colA,colB'; got {spec!r}.")
            raise typer.Exit(code=EXIT_USAGE)
        joint_pairs.append((parts[0], parts[1]))

    if min_grade is not None and min_score is not None:
        _emit_error("specify only one of --min-grade / --min-score, not both.")
        raise typer.Exit(code=EXIT_USAGE)

    if min_grade is not None and min_grade.upper() not in _GRADE_MIN_SCORE:
        _emit_error(f"--min-grade must be one of A, B, C, D; got {min_grade!r}.")
        raise typer.Exit(code=EXIT_USAGE)

    if mode not in ("report", "warn", "fail"):
        _emit_error(f"--mode must be one of report, warn, fail; got {mode!r}.")
        raise typer.Exit(code=EXIT_USAGE)

    strategy_map: dict[str, str] = {}
    if pipeline_config is not None:
        from decoy_engine import PipelineConfig

        try:
            raw_cfg = _yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw_cfg).model_dump()
        except Exception as exc:
            _emit_error(f"could not parse --config {pipeline_config}: {exc}")
            raise typer.Exit(code=EXIT_USAGE)
        strategy_map = _build_strategy_map(config_dict)

    if policy is not None:
        try:
            policy_config = _yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            _emit_error(f"could not parse --policy {policy}: {exc}")
            raise typer.Exit(code=EXIT_USAGE)
        if not isinstance(policy_config, dict):
            _emit_error(f"--policy {policy} must be a YAML/JSON mapping.")
            raise typer.Exit(code=EXIT_USAGE)
    else:
        thresholds: dict[str, Any] = {}
        if min_score is not None:
            thresholds["overall"] = {"min": min_score}
        elif min_grade is not None:
            thresholds["overall"] = {"min": _GRADE_MIN_SCORE[min_grade.upper()]}
        policy_config = {"mode": mode, "thresholds": thresholds}

    import pandas as pd
    from decoy_engine.quality import apply_quality_policy, compute_quality_report

    try:
        src_df = pd.read_csv(source)
    except Exception as exc:
        _emit_error(f"could not read {source}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    try:
        out_df = pd.read_csv(output)
    except Exception as exc:
        _emit_error(f"could not read {output}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    report = compute_quality_report(
        src_df,
        out_df,
        joint_columns=joint_pairs or None,
        expect_row_parity=not generate,
    )
    policy_result = apply_quality_policy(report, policy_config, strategy_map=strategy_map)

    if report_out is not None:
        report_out.write_text(
            json.dumps({**report, "policy": policy_result}, indent=2),
            encoding="utf-8",
        )

    verdict = policy_result["verdict"]
    status = "ok" if verdict == "pass" else verdict

    if state.mode is OutputMode.json:
        envelope = dict(report)
        envelope["command"] = "validate distribution"
        envelope["status"] = status
        envelope["policy"] = policy_result
        emit_json(state, envelope)
    elif state.mode is not OutputMode.quiet:
        _render_distribution_report(state, report, policy_result)

    if verdict == "fail" or (verdict == "warn" and fail_on_warning):
        raise typer.Exit(code=EXIT_FINDINGS)


def _render_distribution_report(
    state: Any,
    report: dict[str, Any],
    policy_result: dict[str, Any],
) -> None:
    """Human-readable rendering of a quality-report/v1 + policy result."""
    from decoy.ui.table import make_table

    grade = report.get("grade", "unavailable")
    overall = report.get("overall_score")
    overall_str = f"{overall:.3f}" if isinstance(overall, (int, float)) else "n/a"
    verdict = policy_result.get("verdict", "pass")

    if verdict == "pass":
        verdict_text = success(verdict.upper())
    elif verdict == "warn":
        verdict_text = warn(verdict.upper())
    else:
        verdict_text = error(verdict.upper())
    state.console.print(verdict_text, f"grade {grade}  overall_score {overall_str}")

    columns = report.get("marginal", {}).get("columns", [])
    if columns:
        table = make_table("Column", "Comparable", "Similarity", title="Marginal fidelity")
        for col in columns:
            if not isinstance(col, dict):
                continue
            sim = col.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            table.add_row(
                str(col.get("column", "?")),
                "yes" if col.get("comparable") else "no",
                sim_str,
            )
        state.console.print(table)

    joints = report.get("pairwise", {}).get("joints", [])
    if joints:
        table = make_table("Joint", "Comparable", "Similarity", title="Pairwise fidelity")
        for j in joints:
            if not isinstance(j, dict):
                continue
            sim = j.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            table.add_row(
                "x".join(j.get("columns", [])),
                "yes" if j.get("comparable") else "no",
                sim_str,
            )
        state.console.print(table)

    violations = policy_result.get("violations", [])
    if violations:
        table = make_table("Check", "Column", "Expected", "Actual", title="Policy violations")
        for v in violations:
            table.add_row(
                str(v.get("check", "?")),
                str(v.get("column", "-")),
                str(v.get("expected", "-")),
                str(v.get("actual", "-")),
            )
        state.console.print(table)
    elif verdict == "pass":
        state.console.print(success("OK"), "no policy violations.")


validate_app.command(name="config", epilog=_CONFIG_EPILOG)(config)
validate_app.command(name="distribution", epilog=_DISTRIBUTION_EPILOG)(distribution)

VALIDATE_EPILOG = _VALIDATE_EPILOG

__all__ = ["VALIDATE_EPILOG", "validate_app"]
