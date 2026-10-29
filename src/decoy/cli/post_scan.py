"""`decoy post-scan` -- check a transformed output against its source.

Post-scan is the third phase (Pre-scan -> Transform -> Post-scan). Each
subcommand is a separate check with its own claim; none is a universal "safe"
verdict and none is a release decision:

  integrity -- residual-PII / FK-preservation / policy findings on a masked file
               (wraps `decoy_engine.verification.run_post_mask`,
               schema `post-scan-integrity/v2`). Report-only.
  fidelity  -- label-free distribution similarity between a source and an output
               (wraps `decoy_engine.quality`). Similarity is a measurement, NOT a
               privacy guarantee.

A check that cannot run exits non-zero; it never reads as a clean pass. The
engine owns every algorithm: this module only loads files, calls the engine and
renders the result. Raw exception text is never echoed (type name only).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperGroup

from decoy.cli import _value_free as vf
from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import error, hint, risk_high, success, warn

# Grade -> minimum overall_score, mirroring the engine's own grade thresholds
# (decoy_engine.quality.report._GRADE_THRESHOLDS: A >= 0.95, B >= 0.85,
# C >= 0.70, D >= 0.50): the engine maps score -> grade but exposes no reverse
# (grade -> score) helper, so `--min-grade` needs its own copy of the table.
_GRADE_MIN_SCORE: dict[str, float] = {"A": 0.95, "B": 0.85, "C": 0.70, "D": 0.50}

_FIDELITY_NOTE = (
    "Fidelity measures statistical similarity between source and output. "
    "It is not a privacy guarantee."
)
_INTEGRITY_NOTE = (
    "Report-only: findings cover the integrity checks that ran. This is not a "
    "release decision or a guarantee that no sensitive data remains."
)

post_scan_app = typer.Typer(
    name="post-scan",
    cls=vf.value_free_usage_errors(TyperGroup),
    help=(
        "Check a transformed output against its source: integrity (residual "
        "PII / FK / policy findings) and fidelity (distribution similarity). "
        "Each check is a separate claim; neither is a release decision."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# CLI: post-scan fidelity SOURCE OUTPUT
# ---------------------------------------------------------------------------

_FIDELITY_EPILOG = """\
Examples:

  decoy post-scan fidelity source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output. Report mode (record only): always exits 0.

  decoy post-scan fidelity source.csv output.csv --config pipeline.yaml
    Pass the pipeline config so intentional loss (hash, bucketize, ...)
    is not flagged as accidental drift.

  decoy post-scan fidelity source.csv synthetic.csv --generate
    Row counts are expected to differ (synthetic generation, not masking).

  decoy post-scan fidelity source.csv output.csv --mode fail --min-grade B
    Exit non-zero (EXIT_FINDINGS) when the overall grade falls below B.

  decoy post-scan fidelity source.csv output.csv --joint state,tier --json
    Include a (state, tier) joint fidelity score; emit the full
    quality-report/v1 + policy JSON.

  decoy post-scan fidelity source.csv output.csv --report-out report.json
    Also write the full report + policy verdict to disk.

Exit codes: 0 pass (or warn without --fail-on-warning); 4 EXIT_FINDINGS
when the policy verdict is fail, or warn with --fail-on-warning set;
1 EXIT_USAGE for bad input (missing columns, unreadable CSV, bad flags).

Fidelity measures statistical similarity only; it is not a privacy guarantee.

See also: decoy post-scan integrity, decoy fit, decoy run.
"""


def _build_strategy_map(config_dict: dict[str, Any]) -> dict[str, str]:
    """Flatten column -> strategy across every declared table.

    Mirrors the evidence manifest's strategy-summary loop
    (`decoy.cli.evidence.build_manifest`). `post-scan fidelity` checks a single
    source/output CSV pair, not a specific table, so this assumes column names
    are unique across the pipeline's declared tables; a multi-table config
    with a repeated column name lets the last table's strategy win. Acceptable
    for the v1 single source/output scope (D4).
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


def _fidelity(
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

    Wraps `decoy_engine.quality.compute_quality_report` +
    `apply_quality_policy` (report.py:97, policy.py:142): the engine owns
    every metric and the letter grade; this command computes no fidelity
    number itself. Reads both CSVs fresh on every invocation (pure,
    repeatable) -- the CLI's local evidence manifest records file
    fingerprints but not the raw frames, so recomputing from the two files
    is the only honest source for this number (BF1).

    Exit codes: 0 when the policy verdict is 'pass' (or 'warn' without
    --fail-on-warning); EXIT_FINDINGS (4) when the verdict is 'fail', or
    'warn' with --fail-on-warning set. This mirrors `post-scan integrity`'s
    exit-code contract -- a data-audit verb that reports findings, not a run
    that crashed -- rather than EXIT_RUNTIME (reserved for the CLI/engine
    blowing up unexpectedly).
    """
    import yaml as _yaml

    state = setup_output(json_, quiet, verbose)

    def _fail(code: str, message: str, exit_code: int = EXIT_USAGE) -> None:
        vf.fail(state, "post-scan fidelity", code, message, exit_code=exit_code)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            _fail(vf.CODE_USAGE, "--joint expects 'colA,colB'.")
        joint_pairs.append((parts[0], parts[1]))

    if min_grade is not None and min_score is not None:
        _fail(vf.CODE_USAGE, "specify only one of --min-grade / --min-score, not both.")

    if min_grade is not None and min_grade.upper() not in _GRADE_MIN_SCORE:
        _fail(vf.CODE_USAGE, "--min-grade must be one of A, B, C, D.")

    if mode not in ("report", "warn", "fail"):
        _fail(vf.CODE_USAGE, "--mode must be one of report, warn, fail.")

    strategy_map: dict[str, str] = {}
    if pipeline_config is not None:
        from decoy_engine import PipelineConfig

        try:
            raw_cfg = _yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw_cfg).model_dump()
        except _yaml.YAMLError as exc:
            # YAMLError carries the offending source line verbatim; sanitize it.
            _fail(vf.CODE_CONFIG_INVALID, sanitize_yaml_error(exc))
        except Exception as exc:
            _fail(vf.CODE_CONFIG_INVALID, f"could not parse --config ({vf.exc_label(exc)}).")
        strategy_map = _build_strategy_map(config_dict)

    if policy is not None:
        try:
            policy_config = _yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        except _yaml.YAMLError as exc:
            _fail(vf.CODE_CONFIG_INVALID, sanitize_yaml_error(exc))
        except Exception as exc:
            _fail(vf.CODE_CONFIG_INVALID, f"could not parse --policy ({vf.exc_label(exc)}).")
        if not isinstance(policy_config, dict):
            _fail(vf.CODE_CONFIG_INVALID, "--policy must be a YAML/JSON mapping.")
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
        _fail(vf.CODE_INPUT_UNREADABLE, f"could not read the source file ({vf.exc_label(exc)}).")
    try:
        out_df = pd.read_csv(output)
    except Exception as exc:
        _fail(vf.CODE_INPUT_UNREADABLE, f"could not read the output file ({vf.exc_label(exc)}).")

    try:
        report = compute_quality_report(
            src_df,
            out_df,
            joint_columns=joint_pairs or None,
            expect_row_parity=not generate,
        )
        policy_result = apply_quality_policy(report, policy_config, strategy_map=strategy_map)
    except Exception as exc:
        # A measurement that could not run is a failure, never a clean pass.
        _fail(vf.CODE_CHECK_FAILED, f"fidelity measurement failed: {vf.exc_label(exc)}", EXIT_RUNTIME)

    if report_out is not None:
        report_out.write_text(
            _json.dumps({**report, "policy": policy_result}, indent=2),
            encoding="utf-8",
        )

    verdict = policy_result["verdict"]
    status = "ok" if verdict == "pass" else verdict

    if state.mode is OutputMode.json:
        envelope = dict(report)
        envelope["command"] = "post-scan fidelity"
        envelope["status"] = status
        envelope["policy"] = policy_result
        envelope["note"] = _FIDELITY_NOTE
        emit_json(state, envelope)
    elif state.mode is not OutputMode.quiet:
        _render_fidelity_report(state, report, policy_result)

    if verdict == "fail" or (verdict == "warn" and fail_on_warning):
        raise typer.Exit(code=EXIT_FINDINGS)


def _render_fidelity_report(
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

    if policy_result.get("mode", "report") == "report":
        # Report mode records a measurement; there is no gate to pass or fail.
        verdict_text = hint("MEASURED (report-only)")
    elif verdict == "pass":
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
    state.console.print(hint("Note:"), _FIDELITY_NOTE)


# ---------------------------------------------------------------------------
# CLI: post-scan integrity MASKED --source SRC
# ---------------------------------------------------------------------------

_INTEGRITY_EPILOG = """\
Examples:

  decoy post-scan integrity masked.csv --source source.csv
    Run all three post-mask checks (residual_pii + fk_preservation +
    policy_validation) against a masked file with its pre-mask
    baseline as ground truth. Render a Rich findings table.

  decoy post-scan integrity masked.csv --source source.csv --config pipeline.yaml
    Same, but load the pipeline YAML so policy_validation can
    compare against the configured masks. Without --config the
    runner still produces residual_pii findings; policy_validation
    is reduced to "no config provided" notes.

  decoy post-scan integrity masked.csv --source source.csv --json > report.json
    Pipe the full post-scan-integrity/v2 report JSON for downstream tooling.

  decoy post-scan integrity masked.csv --source source.csv --output report.json
    Write JSON to file + render a Rich summary on stderr.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy report verify, decoy post-scan fidelity, decoy explain post-scan,
  decoy explain exit-codes.
"""


def _integrity(
    masked: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the masked CSV to verify.",
    ),
    source: Path = typer.Option(
        ...,
        "--source",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Pre-mask source CSV (ground truth for the integrity check).",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Optional pipeline.yaml. When passed, policy_validation can "
            "compare against the configured masks. Without it the runner "
            "still produces residual_pii + fk_preservation findings."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Write the post-scan-integrity/v2 JSON to this path. The Rich table "
            "still renders to stderr."
        ),
    ),
    allow_source_mismatch: bool = typer.Option(
        False,
        "--allow-source-mismatch",
        help=(
            "Suppress the stderr warning when --source does not match "
            "the pipeline's declared sources block."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full post-scan-integrity/v2 JSON to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Verify a masked file's integrity against its pre-mask source.

    Wraps `decoy_engine.verification.run_post_mask`. Runs the three
    post-mask check buckets (residual_pii, fk_preservation,
    policy_validation) a pipeline runs when `post_scan.integrity: true` is
    declared; this verb lets the CLI user run the same checks standalone.

    Report-only: it records findings, it does not repair the output, and a
    clean result is not a release decision. Distinct from `report verify`
    (manifest fingerprint drift): integrity is post-mask residual-PII / FK /
    policy on a masked file plus --source.

    Exit codes: 0 clean; 4 EXIT_FINDINGS on any fail-severity finding;
    1 EXIT_USAGE for missing files; 3 EXIT_RUNTIME for unexpected
    exceptions.
    """
    import pandas as pd

    from decoy.ui.table import make_table

    state = setup_output(json_, quiet, verbose)

    def _fail(code: str, message: str, exit_code: int = EXIT_USAGE) -> None:
        vf.fail(state, "post-scan integrity", code, message, exit_code=exit_code)

    try:
        from decoy_engine.verification import run_post_mask

        source_df = pd.read_csv(source)
        masked_df = pd.read_csv(masked)

        config_dict: dict
        table_name: str
        if config is not None:
            import yaml as _yaml
            from decoy_engine import PipelineConfig

            try:
                raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
            except _yaml.YAMLError as exc:
                # The outer handler renders str(exc); a raw YAMLError there would
                # echo the offending source line. Re-raise a pre-sanitized message.
                _fail(vf.CODE_CONFIG_INVALID, sanitize_yaml_error(exc))
            try:
                config_dict = PipelineConfig.model_validate(raw).model_dump()
            except Exception as exc:
                _fail(
                    vf.CODE_CONFIG_INVALID,
                    f"could not validate --config ({vf.exc_label(exc)}).",
                )
            # Pick the first declared table name. Mixed-mode configs
            # can declare multiple; the CLI verb today handles a single
            # source/masked pair, so we anchor on the first table the
            # pipeline declared and warn if the user passed a source
            # that points elsewhere.
            tables = config_dict.get("tables") or []
            table_name = tables[0]["name"] if tables else masked.stem
            declared_sources = config_dict.get("sources") or {}
            declared_path = None
            if table_name in declared_sources:
                declared_path = declared_sources[table_name].get("path")
            if (
                declared_path
                and not allow_source_mismatch
                and Path(declared_path).resolve() != source.resolve()
            ):
                state.err_console.print(
                    hint("warning:"),
                    "--source does not match the pipeline's declared input.path; "
                    "proceeding with --source as ground truth "
                    "(suppress with --allow-source-mismatch).",
                )
        else:
            # No config: synthesize a minimal dict. The runner's
            # residual_pii + policy_validation branches degrade
            # gracefully when relationships + sources + tables are
            # absent (see the decoy_engine.verification.postmask.runner docstring).
            table_name = masked.stem
            config_dict = {
                "version": 2,
                "global_settings": {"seed": 0},
                "sources": {},
                "tables": [],
                "targets": {},
                "relationships": [],
            }

        report = run_post_mask(
            source_frames={table_name: source_df},
            output_frames={table_name: masked_df},
            config=config_dict,
        )

        if out is not None:
            out.write_text(_json.dumps(report, indent=2))

        # Decide exit code based on the report's severity counters.
        fail_count = int(report.get("fail_count") or 0)
        error_count = int(report.get("error_count") or 0)
        exit_code = EXIT_FINDINGS if (fail_count + error_count) > 0 else 0

        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "post-scan integrity",
                    "status": "ok" if exit_code == 0 else "findings",
                    "note": _INTEGRITY_NOTE,
                    "report": report,
                },
            )
        elif state.mode is not OutputMode.quiet:
            # Render a 3-row summary table; the per-finding detail
            # lives in the JSON payload (--json or --output).
            table = make_table("Bucket", "Findings", "Severities", title="Post-scan integrity")
            for bucket in ("residual_pii", "fk_preservation", "policy_validation"):
                findings = report.get(bucket) or []
                if not findings:
                    table.add_row(bucket, "0", success("clean"))
                    continue
                sevs: dict[str, int] = {}
                for f in findings:
                    sev = (f.get("severity") if isinstance(f, dict) else None) or "info"
                    sevs[sev] = sevs.get(sev, 0) + 1
                sev_text = ", ".join(f"{k}:{v}" for k, v in sorted(sevs.items()))
                table.add_row(bucket, str(len(findings)), sev_text)
            state.console.print(table)
            counters = (
                f"pass={report.get('pass_count', 0)}  "
                f"warning={report.get('warning_count', 0)}  "
                f"fail={fail_count}  "
                f"error={error_count}"
            )
            state.console.print(counters)
            if exit_code == 0:
                state.console.print(
                    success("OK"), "no fail or error findings in the checks that ran."
                )
            else:
                state.console.print(
                    risk_high("FINDINGS"),
                    f"{fail_count + error_count} fail/error findings; review the report.",
                )
            state.console.print(hint("Note:"), _INTEGRITY_NOTE)

        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    except typer.Exit:
        raise
    except FileNotFoundError:
        _fail(vf.CODE_INPUT_UNREADABLE, "could not open an input file (not found).")
    except Exception as exc:
        # Type name only, no traceback even with --verbose: engine/pandas
        # messages and frames can embed raw cell values.
        _fail(vf.CODE_CHECK_FAILED, f"integrity check failed: {vf.exc_label(exc)}", EXIT_RUNTIME)


post_scan_app.command(name="integrity", epilog=_INTEGRITY_EPILOG)(_integrity)
post_scan_app.command(name="fidelity", epilog=_FIDELITY_EPILOG)(_fidelity)
