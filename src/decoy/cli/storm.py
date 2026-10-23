"""`decoy storm integrity` -- verify a masked file against its pre-mask source.

S3a (CLI redesign) emptied this group down to `integrity`. The former
`storm analyze` (pre-run profiling) and its saved-scan subcommands
(`fields`/`show`/`diff`) merged into the top-level `decoy scan` verb; see
`decoy.cli.scan`. `integrity` is post-run verification and stays here as a
transient lone command until it moves to `report integrity` in S4.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import error, hint, risk_high, success

storm_app = typer.Typer(
    name="storm",
    help=(
        "Masked-file verification -- `integrity` checks a masked file against "
        "its pre-mask source (post-run; moves to `report integrity` in S4). "
        "Pre-run profiling now lives in `decoy scan`."
    ),
    no_args_is_help=True,
)


_INTEGRITY_EPILOG = """\
Examples:

  decoy storm integrity masked.csv --source source.csv
    Run all three post-mask checks (residual_pii + fk_preservation +
    policy_validation) against a masked file with its pre-mask
    baseline as ground truth. Render a Rich findings table.

  decoy storm integrity masked.csv --source source.csv --config pipeline.yaml
    Same, but load the pipeline YAML so policy_validation can
    compare against the configured masks. Without --config the
    runner still produces residual_pii findings; policy_validation
    is reduced to "no config provided" notes.

  decoy storm integrity masked.csv --source source.csv --json > report.json
    Pipe the full JobStormReport-shaped JSON for downstream tooling.

  decoy storm integrity masked.csv --source source.csv --output report.json
    Write JSON to file + render a Rich summary on stderr.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy scan, decoy run, decoy explain exit-codes.
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
            "Write the JobStormReport JSON to this path. The Rich table "
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
        help="Emit the full JobStormReport JSON to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Verify a masked file's integrity against its pre-mask source.

    Wraps `decoy_engine.storm.postmask.run_storm_post_mask`. Runs the
    three post-mask check buckets (residual_pii, fk_preservation,
    policy_validation) the platform's mask job already runs when
    `run_storm: true` is declared in the pipeline; this verb lets the
    CLI user run the same checks standalone.

    Exit codes: 0 clean; 4 EXIT_FINDINGS on any fail-severity finding;
    1 EXIT_USAGE for missing files; 3 EXIT_RUNTIME for unexpected
    exceptions.

    OSS.4b (2026-06-02).
    """
    import pandas as pd
    state = setup_output(json_, quiet, verbose)
    masked_str = str(masked)
    source_str = str(source)

    try:
        from decoy_engine.storm.postmask import run_storm_post_mask

        source_df = pd.read_csv(source)
        masked_df = pd.read_csv(masked)

        config_dict: dict
        table_name: str
        if config is not None:
            import yaml as _yaml
            from decoy_engine import PipelineConfig

            raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw).model_dump()
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
                    f"--source {source_str} does not match pipeline "
                    f"input.path {declared_path}; proceeding with --source "
                    "as ground truth (suppress with --allow-source-mismatch).",
                )
        else:
            # No config: synthesize a minimal dict. The runner's
            # residual_pii + policy_validation branches degrade
            # gracefully when relationships + sources + tables are
            # absent (verified against
            # decoy_engine.storm.postmask.runner docstring +
            # tests/unit/storm/test_postmask_runner.py).
            table_name = masked.stem
            config_dict = {
                "version": 1,
                "global_settings": {"seed": 0},
                "sources": {},
                "tables": [],
                "targets": {},
                "relationships": [],
            }

        report = run_storm_post_mask(
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
                    "command": "storm integrity",
                    "status": "ok" if exit_code == 0 else "findings",
                    "masked": masked_str,
                    "source": source_str,
                    "report": report,
                },
            )
        elif state.mode is not OutputMode.quiet:
            # Render a 3-row summary table; the per-finding detail
            # lives in the JSON payload (--json or --output).
            table = make_table("Bucket", "Findings", "Severities", title="Storm integrity")
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
                state.console.print(success("OK"), "no fail or error findings.")
            else:
                state.console.print(
                    risk_high("FINDINGS"),
                    f"{fail_count + error_count} fail/error findings; review the report.",
                )

        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    except typer.Exit:
        raise
    except FileNotFoundError as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "storm integrity",
                    "status": "error",
                    "masked": masked_str,
                    "source": source_str,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_USAGE)
    except Exception as exc:
        error_text = str(exc)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "storm integrity",
                    "status": "error",
                    "masked": masked_str,
                    "source": source_str,
                    "error": error_text,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), error_text)
            state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback.",
            )
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=EXIT_RUNTIME)


# OSS.4b (2026-06-02): post-run integrity verb. CLI wrapper for
# decoy_engine.storm.postmask.run_storm_post_mask.
storm_app.command(name="integrity", epilog=_INTEGRITY_EPILOG)(_integrity)
