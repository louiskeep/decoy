"""`decoy run` -- execute a masking or synthetic-generation pipeline.

CLI.1 commit 3 (2026-06-01): rewired against the V2 engine spine.
Non-chunked runs (the default) go through `run_pipeline`, the engine's
unified entry point that profiles, compiles, and executes mask + generate
tables in one call, using the engine's internal `PandasExecutionAdapter`.
`--chunked` is a separate streaming path (`run_mask_pipeline_chunked`),
mask-only, on the engine's one execution adapter (pandas). `graph` and
`convert` are V1-only and have no engine; the choke-point validator
rejects them with a typed error before this module sees them.

This package holds the Typer command and nothing else. The phases live in `_prepare`,
`_execute`, `_errors`, `_render`, `_evidence`, `_notify`, `_vault` and `_flow`, and share
their state through `_context.RunContext`.
"""

from pathlib import Path

import typer

from decoy import _resources
from decoy.cli.io import resolve_path as _resolve_path
from decoy.cli.run import _flow
from decoy.cli.run._context import Mode, NotifyOn, RunContext
from decoy.cli.run._execute import _load_sources_from_config, _write_mask_outputs
from decoy.cli.run._prepare import _has_kind
from decoy.cli.run._vault import VAULT_WRITE_FAILED
from decoy.ui.output import setup_output

__all__ = [
    "RUN_EPILOG",
    "VAULT_WRITE_FAILED",
    "Mode",
    "NotifyOn",
    "_has_kind",
    "_load_sources_from_config",
    "_resolve_path",
    "_write_mask_outputs",
    "run",
]


_RUN_EPILOG = """\
Examples:

  decoy run pipeline.yaml
    Run with default mode (mask).

  decoy run pipeline.yaml --json
    Suppress chrome and emit a structured result for scripting.

  decoy run pipeline.yaml --chunked --chunk-size 100000
    Stream a large source through the engine instead of loading it whole.
    (See: decoy explain chunked.)

  decoy run pipeline.yaml --vault vault.bin
    Write an encrypted token vault for columns marked `vault: true`, so
    they can be recovered later with `decoy unmask`. (See: decoy explain vault.)

  decoy run pipeline.yaml --chunked
    Stream a large single-table mask in bounded memory (pandas chunked path).
    (Masking uses the pandas substrate. See: decoy explain substrate.)

  decoy run pipeline.yaml --notify webhook:https://hooks.example.com/x
    Notify a webhook after the run reaches its terminal state. Repeatable;
    kind in webhook/slack/email. Best-effort: a channel failure never
    changes the run's exit code. Webhook signing key from
    DECOY_NOTIFY_WEBHOOK_SECRET; SMTP from DECOY_NOTIFY_SMTP_HOST/_PORT/
    _USER/_PASS/_FROM. Nothing is persisted to .decoy/workspace.json.

  decoy run pipeline.yaml --notify slack:https://hooks.slack.com/services/x --notify-on failure
    Only notify on a failed run.

  decoy run pipeline.yaml --explain-plan
    After the run, show the EXECUTION ROUTE the engine chose (sequential /
    full_frame / out_of_core) and why. This is the route decision, not the
    per-column masking rationale -- for that, run
    `decoy validate compile --explain` before the run.

  decoy run pipeline.yaml --fidelity
    After the run, show a quick inline marginal-fidelity check per mask table.
    A low grade never fails the run. For the fuller post-hoc grade, run
    `decoy report fidelity`.

  decoy run pipeline.yaml --post-validate
    After the run, run the post-execution validator suite over the masked
    output and show the findings. Warn-only: the run still exits 0.

  decoy run pipeline.yaml --post-validate-enforce
    Like --post-validate, but exit 4 (findings) when any hard check fails.
    The masked output is still written. (The report flags are not supported
    with --chunked.)

See also: decoy validate compile --explain, decoy report fidelity, decoy validate config, decoy explain chunked, decoy explain vault.
"""


def run(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config.",
    ),
    mode: Mode = typer.Option(
        Mode.mask,
        "--mode",
        "-m",
        help="Operation: mask existing data or generate synthetic data.",
        case_sensitive=False,
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout. Progress goes to stderr.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr; exit code carries success.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
    master_key: str = typer.Option(
        None,
        "--master-key",
        envvar="DECOY_MASTER_KEY",
        help=(
            "64-char hex master key for keyed deterministic SYNTHETIC "
            "GENERATION only (generate_columns:). Same key + same "
            "--key-label always yield bitwise-identical generated output "
            "across runs and machines. Reads DECOY_MASTER_KEY env var when "
            "omitted; without either, generation falls back to the legacy "
            "seeded path (per-input deterministic but not portable). "
            "With a key, global_settings.seed is not used for generated tables "
            "(masked tables still use it). "
            "This flag does NOT affect masking -- masking's keyed "
            "determinism is configured separately via '--mask-secret' (or "
            "the pipeline YAML's 'global_settings.mask_secret_ref'), never "
            "this flag or its env var. See: decoy explain keys."
        ),
    ),
    mask_secret: str = typer.Option(
        None,
        "--mask-secret",
        help=(
            "env:NAME or file:/PATH pointing at a >=32-byte mask secret for "
            "keyed masking (mask: strategies -- fpe, hash, date_shift, and "
            "others). Independent of --master-key (which is generation-only). "
            "Sets 'global_settings.mask_secret_ref' for this run; an error if "
            "the YAML already sets it. Explicit flag only -- it deliberately "
            "has NO env var, because the ref it carries (e.g. "
            "'env:DECOY_MASK_SECRET') already indirects through the "
            "environment; a second env layer would absorb the raw exported "
            "secret as this flag's value. See: decoy explain keys."
        ),
    ),
    chunked: bool = typer.Option(
        False,
        "--chunked",
        help=(
            "Stream the source through the engine chunk-by-chunk, for inputs "
            "too large to load whole. Works for mask configs whose every "
            "strategy is value-keyed (hash, fpe, redact, truncate, "
            "text_redact, date_shift, bucketize), plus faker/categorical "
            "when deterministic with an explicit pool_size / categories "
            "declared in config; output is byte-identical to a plain run. "
            "Sources and targets use their declared format (csv or parquet; fixed_width "
            "and CSV in a zip or tar archive are not supported with --chunked). "
            "See: decoy explain chunked."
        ),
    ),
    chunk_size: int = typer.Option(
        100_000,
        "--chunk-size",
        min=1,
        help="Rows per chunk in --chunked mode.",
    ),
    max_memory: str = _resources.MAX_MEMORY_OPTION,
    threads: str = _resources.THREADS_OPTION,
    vault: Path = typer.Option(
        None,
        "--vault",
        help=(
            "Write the token vault (encrypted source-to-masked map for "
            "vault: true columns) to this path. The vault plus the config "
            "re-identify every vaulted value: store them separately and "
            "never alongside the masked output. Needs the engine's vault "
            "extra (cryptography). Not supported with --chunked."
        ),
    ),
    key_label: str = typer.Option(
        None,
        "--key-label",
        help=(
            "Stable namespace string for the --master-key generation key "
            "hierarchy (synthetic generation only, not masking). Required "
            "when --master-key is set. Pick something durable "
            "(e.g. 'customers_q4'); changing it produces different "
            "generated output. CLI flag only -- PipelineConfig forbids "
            "unknown top-level keys, so there is no YAML equivalent."
        ),
    ),
    evidence_out: Path = typer.Option(
        None,
        "--evidence-out",
        help=(
            "Write a local evidence manifest (JSON) to this path after a "
            "successful run. The manifest records pipeline hash, input/output "
            "file fingerprints, run metadata, and row counts/timings/warnings "
            "where available (these are omitted for --chunked runs). It does "
            "NOT contain raw data values. Use `decoy report verify` to check "
            "the manifest against current files. "
            "See: decoy explain evidence (when available)."
        ),
    ),
    notify: list[str] = typer.Option(
        [],
        "--notify",
        help=(
            "Notify a channel after the run reaches its terminal state. "
            "Repeatable. Spec is 'kind:target': webhook:<url>, slack:<url>, "
            "email:<address>. Best-effort: a channel failure never changes "
            "the run's exit code. Webhook signing key from "
            "DECOY_NOTIFY_WEBHOOK_SECRET (unsigned if unset); SMTP from "
            "DECOY_NOTIFY_SMTP_HOST/_PORT/_USER/_PASS/_FROM. Nothing is "
            "persisted to .decoy/workspace.json -- targets and secrets are "
            "flags/env only, never written to disk."
        ),
    ),
    notify_on: NotifyOn = typer.Option(
        NotifyOn.always,
        "--notify-on",
        help="Which terminal outcome(s) to notify on: success, failure, or always.",
        case_sensitive=False,
    ),
    native: bool = typer.Option(
        False,
        "--native",
        help=(
            "Require that a compiled native kernel actually executed. Refuses "
            "up front (no run) on --chunked or a generate/mixed config, or on an "
            "absent/broken decoy-engine-native companion. Refuses AFTER the run, "
            "before any output is written, if the job finished without positive "
            "compiled-kernel evidence (e.g. an FK table or a table masked only with "
            "passthrough/redact/truncate). "
            "Mutually exclusive with --no-native. See: decoy explain native."
        ),
    ),
    no_native: bool = typer.Option(
        False,
        "--no-native",
        help=(
            "Force the legacy pandas adapter, bypassing the unified slice "
            "entirely -- the documented rollback for native-on-when-present. "
            "Mutually exclusive with --native. See: decoy explain native."
        ),
    ),
    explain_plan: bool = typer.Option(
        False,
        "--explain-plan",
        help=(
            "After the run, show the EXECUTION ROUTE the engine chose "
            "(sequential / full_frame / out_of_core) and why, from the "
            "result's execution_plan metrics. This is the route decision, NOT "
            "the per-column masking rationale -- for that, use "
            "`decoy validate compile --explain` (pre-run). Default off; "
            "report-only, never changes the exit code. Not supported with "
            "--chunked."
        ),
    ),
    fidelity: bool = typer.Option(
        False,
        "--fidelity",
        help=(
            "After the run, show a QUICK inline distribution-fidelity check "
            "per mask table (marginal grade/score), from the result's "
            "fidelity_reports metrics. A low grade NEVER fails the run. For "
            "the fuller post-hoc grade, use `decoy report fidelity`. Default "
            "off; report-only. Not supported with --chunked."
        ),
    ),
    post_validate: bool = typer.Option(
        False,
        "--post-validate",
        help=(
            "After the run, run the post-execution validator suite over the "
            "masked output and show its results (findings + quality summary), "
            "from the result's quality metrics. Warn-only: findings are "
            "reported but the run still exits 0. Use --post-validate-enforce to "
            "exit with findings. Default off. Not supported with --chunked."
        ),
    ),
    post_validate_enforce: bool = typer.Option(
        False,
        "--post-validate-enforce",
        help=(
            "Like --post-validate, but exit EXIT_FINDINGS (4) when the "
            "validator reports any hard-failed check. The masked output is "
            "still written (the mask succeeded; the findings are a data-quality "
            "signal). Implies --post-validate. Default off. Not supported with "
            "--chunked."
        ),
    ),
    duckdb_source: list[str] = typer.Option(
        [],
        "--duckdb-source",
        help=(
            "Read a pipeline input table from a DuckDB database file instead of "
            "a CSV/Parquet/fixed-width file. Repeatable; spec is 'TABLE=DB_PATH', "
            "where TABLE names a table in the pipeline's `tables:` and the "
            "relation of the same name in the DuckDB file. The relation is "
            "acquired read-only (the database is never written) to a temporary "
            "Parquet file, which is then masked on the normal parquet path "
            "(native-on and --chunked apply unchanged). A flag entry overrides "
            "any `sources:` entry the YAML declares for TABLE. Not supported with "
            "--evidence-out yet. Needs no raw SQL: the relation name is the "
            "handle."
        ),
    ),
    otel_endpoint: str = typer.Option(
        None,
        "--otel-endpoint",
        help=(
            "Export OpenTelemetry traces of this run to the OTLP/HTTP traces URL of a "
            "collector you run (also DECOY_OTEL_ENDPOINT). Headers come only from "
            "DECOY_OTEL_HEADERS (name=value,...), which needs https unless the host is "
            "loopback. Standard OTEL_* variables are ignored. Needs decoy-cli\\[otel]."
        ),
    ),
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking or synthetic-generation job described in
    YAML. The engine handles its own logging per the YAML's `logging:`
    section; flags here only affect CLI-side output.

    Before it reads any source rows, `run` runs the whole `decoy validate`
    check (config, compile, preflight). A `--duckdb-source` relation is
    staged first, so the check sees the file the run reads. An error stops
    the run with the exit code
    `decoy validate` gives (1, or 5 for a capacity refusal); warnings are
    counted on stderr and never stop it. There is no flag to skip the check.
    """
    state = setup_output(json_, quiet, verbose)
    _flow.execute(
        RunContext(
            state=state,
            config=config,
            mode=mode,
            json_=json_,
            quiet=quiet,
            verbose=verbose,
            master_key=master_key,
            mask_secret=mask_secret,
            chunked=chunked,
            chunk_size=chunk_size,
            max_memory=max_memory,
            threads=threads,
            vault=vault,
            key_label=key_label,
            evidence_out=evidence_out,
            notify=notify,
            notify_on=notify_on,
            native=native,
            no_native=no_native,
            explain_plan=explain_plan,
            fidelity=fidelity,
            post_validate=post_validate,
            post_validate_enforce=post_validate_enforce,
            duckdb_source=duckdb_source,
            otel_endpoint=otel_endpoint,
        )
    )


# The epilog is wired by __main__ at command registration time; the
# docstring on `run` stays as the help body.
RUN_EPILOG = _RUN_EPILOG
