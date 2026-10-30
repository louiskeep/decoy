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
engine owns every algorithm: this module only loads files and calls the engine.
Every surface (stdout, `--json`, `--output` / `--report-out`, errors,
`--verbose`) carries only the typed projections minted by
`decoy.cli._projections` (`integrity-report/v1`, `fidelity-report/v1`) and
emitted by the `decoy.cli._value_free` Surface. The raw engine reports are
never serialized: they carry table names, engine messages and free text.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperGroup

from decoy.cli import _projections as proj
from decoy.cli import _value_free as vf
from decoy.cli._value_free import Printer, Surface
from decoy.cli.exit_codes import EXIT_FINDINGS
from decoy.ui.theme import error, hint, risk_high, success, warn

# Grade -> minimum overall_score, mirroring the engine's own grade thresholds
# (decoy_engine.quality.report._GRADE_THRESHOLDS: A >= 0.95, B >= 0.85,
# C >= 0.70, D >= 0.50): the engine maps score -> grade but exposes no reverse
# (grade -> score) helper, so `--min-grade` needs its own copy of the table.
_GRADE_MIN_SCORE: dict[str, float] = {"A": 0.95, "B": 0.85, "C": 0.70, "D": 0.50}

_VERBOSE_HELP = "Also print value-free diagnostics on stderr (warning counts, exception type names)."

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


@vf.guarded("post-scan fidelity")
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
        help="Write the value-free fidelity-report/v1 projection to this path.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the value-free fidelity-report/v1 projection as JSON.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Exit code carries the result.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
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

    surface = Surface("post-scan fidelity", json_, quiet, verbose)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            surface.fail("joint_format")
        joint_pairs.append((parts[0], parts[1]))

    if min_grade is not None and min_score is not None:
        surface.fail("grade_and_score")
    if min_grade is not None and min_grade.upper() not in _GRADE_MIN_SCORE:
        surface.fail("grade_invalid")
    if mode not in ("report", "warn", "fail"):
        surface.fail("mode_invalid")

    strategy_map: dict[str, str] = {}
    if pipeline_config is not None:
        from decoy_engine import PipelineConfig

        try:
            raw_cfg = _yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw_cfg).model_dump()
        except _yaml.YAMLError as exc:
            surface.fail("config_not_yaml", exc=exc, location=vf.yaml_location(exc))
        except Exception as exc:
            surface.fail("config_invalid", exc=exc)
        strategy_map = _build_strategy_map(config_dict)

    if policy is not None:
        try:
            policy_config = _yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        except _yaml.YAMLError as exc:
            surface.fail("policy_not_yaml", exc=exc, location=vf.yaml_location(exc))
        except Exception as exc:
            surface.fail("policy_invalid", exc=exc)
        if not isinstance(policy_config, dict):
            surface.fail("policy_not_mapping")
    else:
        thresholds: dict[str, Any] = {}
        if min_score is not None:
            thresholds["overall"] = {"min": min_score}
        elif min_grade is not None:
            thresholds["overall"] = {"min": _GRADE_MIN_SCORE[min_grade.upper()]}
        policy_config = {"mode": mode, "thresholds": thresholds}

    with surface.engine():
        import pandas as pd
        from decoy_engine.quality import apply_quality_policy, compute_quality_report

        try:
            src_df = pd.read_csv(source)
        except Exception as exc:
            surface.fail("source_unreadable", exc=exc)
        try:
            out_df = pd.read_csv(output)
        except Exception as exc:
            surface.fail("output_unreadable", exc=exc)
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
            surface.fail("fidelity_failed", exc=exc)

    projection = proj.fidelity_report(report, policy_result)
    if report_out is not None:
        surface.write(report_out, projection)

    verdict = (projection.body["policy"] or {}).get("verdict")
    surface.emit(projection, status="ok" if verdict == "pass" else (verdict or "error"), render=_render_fidelity)
    if verdict not in ("pass", "warn") or (verdict == "warn" and fail_on_warning):
        raise typer.Exit(code=EXIT_FINDINGS)


def _score_text(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "n/a"


def _render_fidelity(out: Printer, body: Mapping[str, Any]) -> None:
    policy = body["policy"] or {}
    verdict = policy.get("verdict")
    if policy.get("mode") == "report":
        # Report mode records a measurement; there is no gate to pass or fail.
        verdict_text = hint("MEASURED (report-only)")
    elif verdict == "pass":
        verdict_text = success("PASS")
    elif verdict == "warn":
        verdict_text = warn("WARN")
    else:
        verdict_text = error(str(verdict or "unknown").upper())
    out.line(verdict_text, f"grade {body['grade']}  overall_score {_score_text(body['overall_score'])}")

    if body["columns"]:
        out.table(
            "Column",
            "Comparable",
            "Similarity",
            title="Marginal fidelity",
            rows=[
                (str(c["name"]), "yes" if c["comparable"] else "no", _score_text(c["score"]))
                for c in body["columns"]
            ],
        )
    if body["pairs"]:
        out.table(
            "Joint",
            "Comparable",
            "Similarity",
            title="Pairwise fidelity",
            rows=[
                (
                    "x".join(str(c) for c in j["columns"]),
                    "yes" if j["comparable"] else "no",
                    _score_text(j["score"]),
                )
                for j in body["pairs"]
            ],
        )
    violations = policy.get("violations") or []
    if violations:
        out.table(
            "Check",
            "Severity",
            "Expected",
            "Actual",
            title="Policy violations",
            rows=[
                (v["check"], v["severity"], _score_text(v["expected"]), _score_text(v["actual"]))
                for v in violations
            ],
        )
    elif verdict == "pass":
        out.line(success("OK"), "no policy violations.")
    out.line(hint("Note:"), body["note"])


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
    Pipe the value-free integrity-report/v1 projection for downstream tooling
    (counts, rates, closed codes; tables as opaque table-N ids; no messages).

  decoy post-scan integrity masked.csv --source source.csv --output report.json
    Also write the same integrity-report/v1 projection to a file.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy report verify, decoy post-scan fidelity, decoy explain post-scan,
  decoy explain exit-codes.
"""


@vf.guarded("post-scan integrity")
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
            "Write the value-free integrity-report/v1 projection to this path. "
            "The summary table still renders to stdout."
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
        help="Emit the value-free integrity-report/v1 projection to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
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
    surface = Surface("post-scan integrity", json_, quiet, verbose)

    config_dict: dict = {
        "version": 2,
        "global_settings": {"seed": 0},
        "sources": {},
        "tables": [],
        "targets": {},
        "relationships": [],
    }
    # The engine keys frames by table; the name never leaves the engine report,
    # and the projection replaces every table with an opaque id.
    table_name = "masked"
    if config is not None:
        import yaml as _yaml
        from decoy_engine import PipelineConfig

        try:
            raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
        except _yaml.YAMLError as exc:
            surface.fail("config_not_yaml", exc=exc, location=vf.yaml_location(exc))
        except Exception as exc:
            surface.fail("config_invalid", exc=exc)
        try:
            config_dict = PipelineConfig.model_validate(raw).model_dump()
        except Exception as exc:
            surface.fail("config_invalid", exc=exc)
        # The verb handles a single source/masked pair: anchor on the first
        # declared table and warn when --source points elsewhere.
        tables = config_dict.get("tables") or []
        if tables:
            table_name = tables[0]["name"]
        declared = (config_dict.get("sources") or {}).get(table_name) or {}
        declared_path = declared.get("path") if isinstance(declared, dict) else None
        if (
            declared_path
            and not allow_source_mismatch
            and Path(declared_path).resolve() != source.resolve()
        ):
            surface.notice("source_mismatch")

    with surface.engine():
        import pandas as pd
        from decoy_engine.verification import run_post_mask

        try:
            source_df = pd.read_csv(source)
            masked_df = pd.read_csv(masked)
        except FileNotFoundError:
            surface.fail("input_not_found")
        except Exception as exc:
            surface.fail("source_unreadable", exc=exc)
        try:
            report = run_post_mask(
                source_frames={table_name: source_df},
                output_frames={table_name: masked_df},
                config=config_dict,
            )
        except Exception as exc:
            surface.fail("integrity_failed", exc=exc)

    projection = proj.integrity_report(report)
    if out is not None:
        surface.write(out, projection)

    body = projection.body
    # A runner that failed outright is never a clean pass.
    findings = body["fail_count"] + body["error_count"] + (1 if body["pass_failed_with"] else 0)
    surface.emit(
        projection, status="ok" if findings == 0 else "findings", render=_render_integrity
    )
    if findings:
        raise typer.Exit(code=EXIT_FINDINGS)


def _render_integrity(out: Printer, body: Mapping[str, Any]) -> None:
    rows = []
    for bucket in proj.INTEGRITY_BUCKETS:
        summary = body["buckets"][bucket]
        sev_text = ", ".join(f"{k}:{v}" for k, v in summary["severities"].items())
        rows.append((bucket, str(summary["findings"]), sev_text or success("clean")))
    out.table("Bucket", "Findings", "Severities", title="Post-scan integrity", rows=rows)
    out.line(
        f"pass={body['pass_count']}  warning={body['warning_count']}  "
        f"fail={body['fail_count']}  error={body['error_count']}"
    )
    bad = body["fail_count"] + body["error_count"]
    if body["pass_failed_with"]:
        out.line(risk_high("FAILED"), f"the integrity pass did not run ({body['pass_failed_with']}).")
    elif bad == 0:
        out.line(success("OK"), "no fail or error findings in the checks that ran.")
    else:
        out.line(risk_high("FINDINGS"), f"{bad} fail/error findings; review the report.")
    out.line(hint("Note:"), body["note"])


post_scan_app.command(name="integrity", epilog=_INTEGRITY_EPILOG)(_integrity)
post_scan_app.command(name="fidelity", epilog=_FIDELITY_EPILOG)(_fidelity)
