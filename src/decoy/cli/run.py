"""`decoy run` -- execute a masking or synthetic-generation pipeline.

CLI.1 commit 3 (2026-06-01): rewired against the V2 engine spine.
Non-chunked runs (the default) go through `run_pipeline`, the engine's
unified entry point that profiles, compiles, and executes mask + generate
tables in one call, using the engine's internal `PandasExecutionAdapter`.
`--chunked` is a separate streaming path (`run_mask_pipeline_chunked`),
mask-only, on the engine's pandas adapter. `graph` and `convert` are V1-only and have
no engine; the choke-point validator rejects them with a typed error
before this module sees them.
"""

import binascii
import json as _json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import typer
from rich.text import Text

from decoy import __version__ as _cli_version
from decoy import _native_gate
from decoy.cli._sources import iter_source_chunks, read_source
from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_FINDINGS, EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.extras import (
    MissingExtraError,
    UnsupportedCloudEndpointError,
    check_cloud_endpoints,
    check_cloud_endpoints_supported,
    translate_missing_extra,
    translate_ner_unavailable,
)
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import live_status
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, success, warn

# OOM checker v1: the engine's out-of-core-FK memory gate raises `ExecutionError`
# with exactly one of these two codes when it refuses a job for capacity, never
# any other reason -- matched narrowly so a routing/compat/orphan-FK
# `ExecutionError` (any other code) keeps its existing EXIT_RUNTIME
# classification below. See docs/plans/2026-07-24-oom-checker-cli-v1.md R8.
# `out_of_core_insufficient_memory` is now LEGACY-ENGINE compat (round-4, engine
# side): a current engine's build-floor gate is advisory and never raises it, so
# this code only ever arrives from an older engine still running the pre-round-4
# hard-fail gate; kept recognized here rather than dropped so the CLI stays
# correct against that older engine too.
_CAPACITY_CODES = frozenset({"out_of_core_insufficient_memory", "out_of_core_fanin_exceeds_budget"})


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"


class NotifyOn(str, Enum):
    success = "success"
    failure = "failure"
    always = "always"


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
    (See: decoy explain chunked.)

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


class _VaultUsageError(Exception):
    """--vault on a config that cannot vault; user error (exits EXIT_USAGE)."""


class _ChunkedGenerateError(Exception):
    """--chunked with a generate-table config; user error (exits EXIT_USAGE)."""


class _ChunkedFixedWidthError(Exception):
    """--chunked with a fixed_width source; user error (exits EXIT_USAGE)."""


class _ChunkedReportFlagError(Exception):
    """--chunked combined with a report flag (--explain-plan / --fidelity /
    --post-validate[-enforce]); user error (exits EXIT_USAGE).

    S5 (2026-10-23): the four report flags surface fields of the non-chunked
    `run_pipeline`'s `ExecutionResult.quality_metrics`. The `--chunked` path
    (`_run_chunked_mask`) streams mask-only and returns no `ExecutionResult`,
    so there is nothing to read those fields off. Reject the combination
    loudly rather than silently dropping the requested report (plan P2-3)."""


class _MaskSecretUsageError(Exception):
    """--mask-secret AND YAML mask_secret_ref both set; user error (exits EXIT_USAGE)."""


class _ConfigValidationError(Exception):
    """The pipeline YAML failed PipelineConfig schema validation (unknown key
    under extra="forbid", wrong-typed / missing field). A raw Pydantic
    ValidationError caught NARROWLY at the model_validate call site and
    re-raised as this typed error, so the run-level handler classifies it
    EXIT_USAGE without also catching internal engine ValidationErrors raised
    deeper in the pipeline (which are engine defects -> EXIT_RUNTIME)."""


# DE-02: the ONE place that decides whether a mask_secret_ref value is
# well-formed. A valid ref is a non-empty `env:NAME` / `file:/PATH` string; a
# non-str (list/int/dict), empty string, or wrong-prefix string is invalid.
# Shared by the raw pre-check (before Pydantic) and the merged effective-ref
# guard so the two can never diverge. Callers ALWAYS raise a redacted error --
# they never echo the value, which may be a raw secret.
def _is_valid_mask_secret_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("env:", "file:"))


def _load_raw_config(config_path: Path) -> dict | None:
    """Single defensive YAML parse for the pre-flight helpers.

    Audit L3 (2026-06-12): the config was read + parsed up to 4x per
    run (_detect_mode, the spinner body, the follow-up hint, and a
    since-removed key_label reader) -- a perf cliff on large or
    network-mounted configs. Helpers now share one parse; the spinner
    body still re-raises real parse errors through its own load so
    the error path is unchanged.
    """
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None


def run(
    configs: list[Path] = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to the YAML pipeline config. Several paths run as a batch: each in its own "
            "process, --jobs at a time, each with its own run record (see decoy explain progress)."
        ),
    ),
    jobs: int = typer.Option(
        1,
        "--jobs",
        "-j",
        min=1,
        help="How many configs of a batch run at once (default 1). Ignored for a single config.",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="Batch only: re-render the batch's run status every second on a TTY until it finishes.",
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
            "Sources are read by their declared format (csv or parquet; fixed_width is "
            "not supported with --chunked); targets are written by file suffix. "
            "See: decoy explain chunked."
        ),
    ),
    chunk_size: int = typer.Option(
        100_000,
        "--chunk-size",
        min=1,
        help="Rows per chunk in --chunked mode.",
    ),
    vault: Path = typer.Option(
        None,
        "--vault",
        help=(
            "Write the token vault (encrypted source-to-masked map for "
            "vault: true columns) to this path. The vault plus the config "
            "re-identify every vaulted value: store them separately and "
            "never alongside the masked output. Needs the engine's vault "
            "extra (cryptography)."
        ),
    ),
    threads: int = typer.Option(
        None,
        "--threads",
        help=(
            "Threads granted to the engine's compiled native kernels on this run. "
            "Default: min(4, host cores) when the native companion is installed, "
            "else 1. Only the native routes use it; the pandas oracle and --chunked "
            "ignore it. Must be a positive integer."
        ),
    ),
    progress: str = typer.Option(
        "auto",
        "--progress",
        help=(
            "How to show progress: 'auto' (a live status line on a TTY, nothing otherwise), "
            "'jsonl' (one JSON event per line on stderr, works without a TTY and alongside "
            "--json), or 'none'. Events carry phases, the route, per-table row counts and "
            "rates, and the terminal state; never data values."
        ),
    ),
    progress_file: Path = typer.Option(
        None,
        "--progress-file",
        help="Append the JSONL progress events to this file (in addition to --progress).",
    ),
    run_id: str = typer.Option(
        None,
        "--run-id",
        help=(
            "Identifier for this run's local record (default: a UTC stamp plus a random "
            "suffix). Records live under $DECOY_HOME/runs (default ~/.decoy/runs) and are "
            "what `decoy status` reads."
        ),
    ),
    no_record: bool = typer.Option(
        False,
        "--no-record",
        help="Do not write a local run record for this run.",
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
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking or synthetic-generation job described in
    YAML. The engine handles its own logging per the YAML's `logging:`
    section; flags here only affect CLI-side output.
    """
    state = setup_output(json_, quiet, verbose)
    if len(configs) > 1:
        raise typer.Exit(
            code=_run_batch(
                state,
                configs,
                jobs=jobs,
                watch=watch,
                run_id=run_id,
                options=dict(
                    mode=mode,
                    master_key=master_key,
                    mask_secret=mask_secret,
                    chunked=chunked,
                    chunk_size=chunk_size,
                    threads=threads,
                    key_label=key_label,
                    notify=notify,
                    notify_on=notify_on,
                    native=native,
                    no_native=no_native,
                    explain_plan=explain_plan,
                    fidelity=fidelity,
                    post_validate=post_validate,
                    post_validate_enforce=post_validate_enforce,
                    no_record=no_record,
                    vault=vault,
                    evidence_out=evidence_out,
                    progress_file=progress_file,
                ),
            )
        )
    config = configs[0]
    config_str = str(config)

    # Parse --notify specs BEFORE the run (D3): a bad spec is a usage error
    # the user can fix, never a run failure. Notification is a side effect
    # appended after the run reaches its terminal state; it must never
    # change what the run itself does.
    notify_channels = []
    if notify:
        from decoy.notify import NotifySpecError, parse_notify_spec

        try:
            notify_channels = [parse_notify_spec(spec) for spec in notify]
        except NotifySpecError as exc:
            msg = str(exc)
            if state.mode is OutputMode.json:
                emit_json(
                    state,
                    {"command": "run", "status": "error", "config": config_str, "error": msg},
                )
            elif state.mode is not OutputMode.quiet:
                state.err_console.print(error("error:"), msg)
            raise typer.Exit(code=EXIT_USAGE)

    try:
        native_threads = _native_gate.resolve_native_threads(threads)
    except ValueError as exc:
        msg = str(exc)
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "run", "status": "error", "config": config_str, "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    if progress not in ("auto", "jsonl", "none"):
        msg = f"--progress must be one of auto, jsonl, none; got {progress!r}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "run", "status": "error", "config": config_str, "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    raw_cfg = _load_raw_config(config)
    yaml_mode = _detect_mode(raw_cfg) or mode.value

    resolver = _build_resolver(master_key, key_label, raw_cfg, state)

    # Sentinels for evidence manifest building (set on successful plain run).
    _ev_config_dict: dict | None = None
    _ev_engine_version: str | None = None
    _ev_row_counts: dict | None = None
    _ev_timings: tuple = ()
    _ev_engine_warnings: tuple = ()
    # Row count for the --notify event; unconditional (unlike _ev_row_counts,
    # which only fills for --evidence-out). None for --chunked runs (no
    # ExecutionResult to count).
    _notify_row_count: int | None = None
    # Native route classification (Phase 3.1), set on a successful run for
    # the run-summary line and JSON record.
    _native_route: _native_gate.RouteClassification | None = None

    # S5 report flags. `post_validation` is on when EITHER post-validate flag
    # is set (--post-validate-enforce implies --post-validate); it feeds the
    # engine kwarg. `_report_flags` gates the --chunked rejection below. The
    # non-chunked branch stamps `_report_quality_metrics` so the tail can
    # render the requested sections and apply the enforce -> EXIT_FINDINGS map.
    post_validation = post_validate or post_validate_enforce
    _report_flags = explain_plan or fidelity or post_validation
    _report_quality_metrics: dict | None = None

    _record = None if no_record else _open_run_record(state, config, yaml_mode, run_id)

    _run_started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    try:
        with (
            live_status(state, f"Running {yaml_mode}...") as _live,
            _progress_binding(
                record=_record,
                live=_live,
                progress=progress,
                progress_file=progress_file,
                config_label=str(config),
            ),
        ):
            from decoy_engine import (
                PipelineConfig,
                run_pipeline,
            )
            from decoy_engine import (
                __version__ as engine_version,
            )

            if raw_cfg is not None:
                raw = raw_cfg
            else:
                # The defensive parse failed; re-parse here so the real
                # YAML error surfaces through the normal error path.
                import yaml as _yaml

                try:
                    raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
                except _yaml.YAMLError as exc:
                    # A raw YAMLError rides str(exc) through the run-level
                    # handler and echoes the offending source line (which may
                    # hold a secret). Re-raise a pre-sanitized EXIT_USAGE error.
                    raise _ConfigValidationError(sanitize_yaml_error(exc)) from None

            # DE-02 secret-disclosure ROOT guard: validate the RAW YAML
            # `mask_secret_ref` BEFORE PipelineConfig.model_validate(raw). A
            # wrong-type value (list/int/dict/...) would otherwise raise a
            # Pydantic ValidationError whose message echoes `input_value` --
            # i.e. the secret -- and that error is not classified EXIT_USAGE, so
            # it would exit 3 and print the secret via str(exc). Catching it
            # here with a redacted usage error means no mask_secret_ref value
            # (string or not) ever reaches Pydantic's diagnostics. YAML-only:
            # the --mask-secret flag is always a str from Typer.
            _raw_gs = raw.get("global_settings") if isinstance(raw, dict) else None
            # A non-dict `global_settings` (e.g. a YAML list) is malformed AND
            # could smuggle a mask_secret_ref value nested where the dict-path
            # check below can't see it -- Pydantic would then echo that value in
            # its ValidationError. Reject a present-but-non-mapping
            # global_settings here, with a redacted message, before
            # model_validate ever sees the raw structure.
            if _raw_gs is not None and not isinstance(_raw_gs, dict):
                raise _MaskSecretUsageError(
                    "global_settings must be a mapping (a YAML block of "
                    f"key: value pairs), not a {type(_raw_gs).__name__}. "
                    "See: decoy explain keys."
                )
            _raw_ref = _raw_gs.get("mask_secret_ref") if isinstance(_raw_gs, dict) else None
            if _raw_ref is not None and not _is_valid_mask_secret_ref(_raw_ref):
                raise _MaskSecretUsageError(
                    "Invalid global_settings.mask_secret_ref: expected an "
                    "'env:NAME' or 'file:/PATH' reference to a >=32-byte secret. "
                    "It is a REFERENCE, never the raw secret. "
                    "See: decoy explain keys."
                )

            # Catch the schema ValidationError NARROWLY here (not in the
            # run-level except) so ONLY user-config validation maps to
            # EXIT_USAGE; a Pydantic error raised deeper in the engine (e.g.
            # internal registry/capability models) stays an EXIT_RUNTIME defect.
            # str(exc) is safe to surface: the mask_secret_ref ROOT guard above
            # already rejected any secret-bearing structure before this point,
            # and the F8 message cap bounds the rest.
            try:
                from pydantic import ValidationError as _PydanticValidationError

                config_dict = PipelineConfig.model_validate(raw).model_dump()
            except _PydanticValidationError as exc:
                raise _ConfigValidationError(str(exc)) from exc

            # Cloud (s3/gcs) sources/targets are refused inside the shared
            # I/O helpers below (_load_sources_from_config /
            # _run_chunked_mask / _write_mask_outputs, via
            # _require_local_io_endpoints), not here, so `decoy.mask()` --
            # which calls the same helpers -- gets the identical refusal.

            # DE-02 Option B (2026-07-15): --mask-secret sets the same
            # `global_settings.mask_secret_ref` slot the YAML can set directly.
            # It feeds run_pipeline's fail-closed KeyProvider resolution AND
            # the --chunked path (both read mask_secret_ref off this same
            # config dict -- _pipeline.py / _chunked.py); one injection point
            # covers both routes.
            #
            # Both-set check uses PRESENCE (`is not None`), not truthiness: a
            # YAML `mask_secret_ref: ""` is still a configured slot, so the flag
            # must not silently override it -- one secret source per run, chosen
            # explicitly. The flag itself has no env var, so `mask_secret is
            # None` here means "flag absent".
            if mask_secret is not None:
                existing_ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
                if existing_ref is not None:
                    raise _MaskSecretUsageError(
                        "--mask-secret was passed but the YAML already sets "
                        "global_settings.mask_secret_ref. Set the masking "
                        "secret in exactly one place: drop --mask-secret, or "
                        "remove mask_secret_ref from the config."
                    )
                config_dict.setdefault("global_settings", {})["mask_secret_ref"] = mask_secret

            # Validate + fail-closed guard on the EFFECTIVE ref (whether it came
            # from --mask-secret or the YAML). Keyed off PRESENCE, not
            # truthiness: a configured-but-empty `mask_secret_ref: ""` is a user
            # error, NOT a silent fall-through to an unkeyed (job_seed) run --
            # the engine's resolvers treat empty as no-secret, so truthiness
            # here would let an empty ref emit UNKEYED output pre-GA. A present
            # ref must be a well-formed `env:`/`file:` reference.
            #
            # Never echo the ref VALUE in any error (it may be a raw secret a
            # user pasted by mistake): the message states the expected format
            # only. This also keeps the value out of the --json error payload,
            # which is built from `str(exc)`.
            effective_ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
            if effective_ref is not None:
                if not _is_valid_mask_secret_ref(effective_ref):
                    raise _MaskSecretUsageError(
                        "Invalid mask secret: expected an 'env:NAME' or "
                        "'file:/PATH' reference to a >=32-byte secret (from "
                        "--mask-secret or global_settings.mask_secret_ref). It "
                        "is a REFERENCE, never the raw secret. "
                        "See: decoy explain keys."
                    )
                # A mask_secret_ref is only honored by a DE-02 engine; a
                # pre-DE-02 engine has no `keyprovider` module and would
                # SILENTLY IGNORE the ref, emitting job-seed-keyed output
                # (fail-open). The pyproject floor (decoy-engine>=0.4.0, DE-02's
                # release marker) is the first line of defense; this runtime
                # probe is defense-in-depth against a broken or forced install
                # that satisfies the resolver but lacks keyprovider -- refuse
                # the run rather than leak an unkeyed artifact.
                try:
                    import decoy_engine.keyprovider  # noqa: F401
                except ImportError as exc:
                    raise _MaskSecretUsageError(
                        "a mask secret is configured (mask_secret_ref / "
                        "--mask-secret) but the installed decoy-engine is too "
                        "old to honor it -- it has no DE-02 keyprovider, so it "
                        "would silently emit UNKEYED output. Upgrade to "
                        "decoy-engine>=0.4.0 (with DE-02). See: decoy explain keys."
                    ) from exc

            _ev_config_dict = config_dict
            _ev_engine_version = engine_version

            # FC-1 (2026-06-26): run_pipeline is now wired as the single
            # non-chunked entry for all config shapes (mask-only, generate-
            # only, and mixed). The engine handles profiling, planning, the
            # FK graph, and sequencing (generate first, then mask with
            # generate outputs merged into sources). The old split between
            # `generate_tables` and `PandasExecutionAdapter.run` is removed.
            tables_list = config_dict.get("tables") or []
            any_generate = any(
                isinstance(t, dict) and t.get("generate_columns") for t in tables_list
            )

            # Chunked mask streaming is mask-only. Reject loudly when the
            # config has any generate-kind table so the operator gets a clear
            # message instead of silently skipping those tables.
            if chunked and any_generate:
                raise _ChunkedGenerateError(
                    "--chunked is only supported for mask-only configs; "
                    "this config includes generate tables (generate_columns:). "
                    "Run without --chunked to execute a mixed or generate pipeline."
                )

            # S5 (P2-3): the report flags read fields of the non-chunked
            # run_pipeline's ExecutionResult.quality_metrics; the chunked path
            # returns no ExecutionResult, so the flags have nothing to render.
            # Reject the combination up front rather than silently no-op.
            if chunked and _report_flags:
                _requested = [
                    name
                    for name, on in (
                        ("--explain-plan", explain_plan),
                        ("--fidelity", fidelity),
                        ("--post-validate", post_validate),
                        ("--post-validate-enforce", post_validate_enforce),
                    )
                    if on
                ]
                raise _ChunkedReportFlagError(
                    f"--chunked cannot be combined with {', '.join(_requested)}: "
                    "the report flags surface fields of the non-chunked run's "
                    "ExecutionResult, which the streaming --chunked path does not "
                    "produce. Run without --chunked to use these flags."
                )

            # The engine has no bounded fixed-width iterator, so a chunked
            # run cannot stream one. Refuse before any table is written
            # rather than part-way through a multi-table config.
            if chunked:
                _fw_tables = sorted(
                    str(_n)
                    for _n, _s in (config_dict.get("sources") or {}).items()
                    if isinstance(_s, dict) and _s.get("format") == "fixed_width"
                )
                if _fw_tables:
                    raise _ChunkedFixedWidthError(
                        "--chunked cannot read format: fixed_width sources "
                        f"({', '.join(_fw_tables)}); the engine has no streaming "
                        "fixed-width reader. Run without --chunked."
                    )

            # A cheap, no-secret-access check: whether --vault was passed
            # AND at least one column declares it. Computed before
            # constructing the real vault writer (which resolves key
            # material) so the flag-conflict and native-gate usage checks
            # below run first -- a usage error should never wait on a
            # secret-reading side effect.
            vault_columns_declared = False
            if vault is not None:
                from decoy_engine.vault import iter_vault_columns

                vault_columns_declared = bool(iter_vault_columns(config_dict))
                if not vault_columns_declared:
                    raise _VaultUsageError(
                        "--vault was passed but no column declares vault: true "
                        "in this config. Add `vault: true` to the columns whose "
                        "source values the vault should record."
                    )

            # Phase 3.1: resolve --native/--no-native intent and run the
            # shared pre-execution gate (approach 2 Stage 0/1, plus the
            # broken-companion classification of approach 3) BEFORE any
            # dispatch. `vault_active` must be known here (not just visible
            # in the config's `vault: true` columns): admission declines
            # ANY job with a live vault writer regardless of column markers,
            # so the fail-closed scoping needs the real runtime state, not a
            # config-shape proxy. Using `vault_columns_declared` here (not
            # the constructed writer) is equivalent for this decision --
            # `--vault` always fails closed above unless a vault column
            # exists, so "the flag was given and validated" already implies
            # "a writer will exist" -- without paying for key resolution
            # before the gate has had its say.
            if native and no_native:
                raise _native_gate.NativeGateError(
                    "--native and --no-native are mutually exclusive.",
                    code="native_flag_conflict",
                )
            native_intent: _native_gate.NativeIntent = (
                "require" if native else "disable" if no_native else "default"
            )
            gate_result = _native_gate.pre_execution_gate(
                intent=native_intent,
                chunked=chunked,
                any_generate=any_generate,
                config_dict=config_dict,
                vault_active=vault is not None and vault_columns_declared,
            )
            if gate_result.info_message and state.mode is not OutputMode.quiet:
                # Wrapped in Text(): a gate message is free text (e.g. a
                # remediation hint), which Rich's default string markup
                # parsing could otherwise reinterpret.
                state.err_console.print(hint("native:"), Text(gate_result.info_message))
            if gate_result.warn_message and state.mode is not OutputMode.quiet:
                state.err_console.print(warn("warning:"), Text(gate_result.warn_message))

            vault_writer = None
            if vault is not None:
                from decoy_engine import vault_writer_for_config

                vault_writer = vault_writer_for_config(config_dict)

            if chunked:
                resolved_substrate = _run_chunked_mask(
                    config_dict, config.parent, chunk_size, vault_writer=vault_writer
                )
                _native_route = _native_gate.classify_route(
                    chunked=True,
                    any_generate=any_generate,
                    resolved_substrate=resolved_substrate,
                    quality_metrics=None,
                )
            else:
                sources = _load_sources_from_config(config_dict, config.parent)
                instance_locale = (config_dict.get("global_settings") or {}).get("default_locale")
                # S5 report kwargs are passed ONLY when a report flag was
                # requested. All four default off, so the default run sends no
                # new kwargs -- keeping the hot path byte-identical and
                # preserving compatibility with an older engine whose
                # `run_pipeline` predates these parameters (the native-compat
                # contract in test_run_native). When a flag IS set the user has
                # opted into the engine feature and a too-old engine surfacing a
                # TypeError is the honest outcome.
                _report_kwargs = (
                    {
                        "explain_plan": explain_plan,
                        "fidelity_report": fidelity,
                        "post_validation": post_validation,
                        "post_validation_enforce": post_validate_enforce,
                    }
                    if _report_flags
                    else {}
                )
                result = run_pipeline(
                    config_dict,
                    sources,
                    engine_version=engine_version,
                    derive_key=resolver,
                    instance_default_locale=instance_locale,
                    vault_writer=vault_writer,
                    **_report_kwargs,
                    **_native_gate.run_pipeline_kwargs(gate_result),
                    **_native_gate.native_threads_kwargs(native_threads),
                )
                _native_route = _native_gate.classify_route(
                    chunked=False,
                    any_generate=any_generate,
                    resolved_substrate=None,
                    quality_metrics=result.quality_metrics,
                )
                # Stage 2 (approach 2): assert --native's compiled-kernel
                # evidence BEFORE the first write on this path. A no-op for
                # default/--no-native intent.
                _native_gate.post_run_verify(intent=native_intent, route=_native_route)
                _write_mask_outputs(config_dict, result, config.parent)
                # S5: capture the quality metrics so the tail can render the
                # requested report sections and apply the enforce -> EXIT_FINDINGS
                # mapping. The mask has already succeeded and its outputs are
                # written above; enforce only changes the EXIT CODE, never whether
                # output is produced (plan P1-2 -- the engine never fails the job).
                # Captured unconditionally: the data-checks card (validators,
                # quarantine, row errors) renders whether or not a report flag
                # was requested, because quarantine removes rows from the
                # written output and that must never be silent.
                _report_quality_metrics = dict(result.quality_metrics)
                if evidence_out is not None:
                    _ev_row_counts = {name: len(tbl) for name, tbl in result.outputs.items()}
                _ev_timings = result.timings
                _ev_engine_warnings = result.warnings
                _notify_row_count = sum(len(tbl) for tbl in result.outputs.values())
            if vault_writer is not None:
                vault_writer.write(vault)
    except typer.Exit as exc:
        # CLI QA fix (2026-06-02, F7): an inner call site that raises
        # typer.Exit (e.g. a library that vendored Typer) has already
        # set its intended exit code. Do not swallow it into the
        # EXIT_RUNTIME catch-all below.
        _finish_record(_record, "error", getattr(exc, "exit_code", EXIT_RUNTIME), "Exit")
        raise
    except KeyboardInterrupt:
        _finish_record(_record, "interrupted", 130, "KeyboardInterrupt")
        raise
    except Exception as exc:
        _finish_record(_record, "error", None, type(exc).__name__)
        # Audit H10 (2026-06-12): dispatch on exception type so scripts
        # can tell "your config is wrong" (EXIT_USAGE, per the
        # exit_codes.py contract) from "the run blew up" (EXIT_RUNTIME).
        # Imported lazily to keep the engine import off the help path.
        from decoy_engine import ConfigError, PipelineValidationError
        from decoy_engine.plan import PlanCompileError

        # CLI install DX (2026-09-25): a pipeline step that lazily imports an
        # optional dependency (boto3/google-cloud-storage for a cloud
        # source/target, spacy for NER, etc.) raises ImportError when the
        # matching decoy-cli extra isn't installed. Translate that into the
        # exact install line instead of a raw traceback. An ImportError for
        # anything NOT a known optional extra is left as-is (stays classified
        # EXIT_RUNTIME below -- that is a real defect, not a missing extra).
        if isinstance(exc, ImportError):
            _missing_extra = translate_missing_extra(exc)
            if _missing_extra is not None:
                exc = _missing_extra

        # CLI install DX (2026-09-25): the engine's own NerUnavailableError
        # (text_mask/text_redact `ner`) already fails closed for a missing
        # spaCy install; rewrite it to point at decoy-cli's own `[ner]`
        # extra instead of `decoy-engine[ner]` (see translate_ner_unavailable
        # docstring for why only the "spaCy absent" case is rewritten).
        _translated_ner = translate_ner_unavailable(exc)
        if _translated_ner is not None:
            exc = _translated_ner

        # A NerUnavailableError this session's engine build has (defensive
        # import: an older engine just never matches) but that
        # translate_ner_unavailable declined to rewrite -- e.g.
        # ner_model_not_installed, spaCy itself IS present, just not the
        # requested model, so the fix is `spacy download <model>`, not an
        # extra -- still needs EXIT_USAGE classification below with the
        # engine's own message intact.
        try:
            from decoy_engine.storm.ner import NerUnavailableError as _NerUnavailableError

            _ner_unavailable_types: tuple = (_NerUnavailableError,)
        except ImportError:
            _ner_unavailable_types = ()

        # DE-02: MaskSecretError lives in the engine's `keyprovider` module,
        # which a pre-DE-02 engine lacks. Import defensively so a missing
        # module never crashes the error handler itself (it would mask the
        # real exception). `()` makes the isinstance check below a harmless
        # no-op when the class is unavailable.
        try:
            from decoy_engine.keyprovider import MaskSecretError as _MaskSecretError

            _mask_secret_error_types: tuple = (_MaskSecretError,)
        except ImportError:
            _mask_secret_error_types = ()

        # OOM checker v1 (Part A): ExecutionError's two capacity-refusal codes
        # get their own exit code and JSON error_kind, distinct from a generic
        # engine crash. Same defensive-import posture as MaskSecretError above
        # -- an engine too old to have ExecutionError at all just never
        # matches, so this never crashes the error handler itself.
        try:
            from decoy_engine.execution import ExecutionError as _ExecutionError

            _execution_error_types: tuple = (_ExecutionError,)
        except ImportError:
            _execution_error_types = ()

        capacity_code: str | None = None
        if isinstance(exc, _execution_error_types) and exc.code in _CAPACITY_CODES:
            capacity_code = exc.code

        # Phase 3.1: `NativeGateError.code` distinguishes a usage refusal
        # (--native/--no-native conflict, an ineligible shape) from a
        # companion-health refusal (`native_require_<reason>` /
        # `native_companion_<reason>`) -- put it in the JSON envelope so a
        # script can branch on it without parsing `error` text.
        native_code: str | None = None
        if isinstance(exc, _native_gate.NativeGateError):
            native_code = exc.code

        if capacity_code is not None:
            _exit_code = EXIT_CAPACITY
        else:
            _exit_code = (
                EXIT_USAGE
                if isinstance(
                    exc,
                    (
                        PlanCompileError,
                        PipelineValidationError,
                        ConfigError,
                        _ChunkedGenerateError,
                        _ChunkedFixedWidthError,
                        _ChunkedReportFlagError,
                        _VaultUsageError,
                        _MaskSecretUsageError,
                        # CLI install DX: a pipeline step hit an optional
                        # extra that isn't installed -- the operator's
                        # environment is missing a capability their config
                        # calls for, not a runtime crash.
                        MissingExtraError,
                        # A cloud source/target `decoy run`
                        # cannot execute against -- the operator's config
                        # asks for a capability the CLI doesn't have yet,
                        # not a runtime crash.
                        UnsupportedCloudEndpointError,
                        # ner_model_not_installed and any other
                        # NerUnavailableError code not already rewritten
                        # above -- still a fixable environment gap, not an
                        # engine defect.
                        *_ner_unavailable_types,
                        # Phase 3.1: every `NativeGateError` (a --native/
                        # --no-native usage refusal, an absent/broken
                        # companion, or --native's post-run evidence check)
                        # is something the caller can fix by changing the
                        # request, not a CLI/engine defect.
                        _native_gate.NativeGateError,
                        # PipelineConfig.model_validate's ValidationError, caught
                        # narrowly at its call site and re-raised as this typed
                        # error, means the YAML is structurally wrong (unknown key
                        # under extra="forbid", wrong-typed / missing field) -- the
                        # user's config is bad, not a runtime crash. Narrow by
                        # design: a Pydantic error raised deeper in the engine is
                        # NOT reclassified and stays an EXIT_RUNTIME defect.
                        _ConfigValidationError,
                        # DE-02: a bad/missing/weak --mask-secret ref (or YAML
                        # mask_secret_ref) resolves to MaskSecretError (and its
                        # subclasses MissingMaskSecret / WeakMaskSecret /
                        # KeyedStrategyRequiresSecret) -- the operator's config is
                        # wrong, not a runtime crash.
                        *_mask_secret_error_types,
                    ),
                )
                else EXIT_RUNTIME
            )
        # CLI QA fix (2026-06-02, F8): cap the error message at 500
        # chars before emitting through --json. Engine exceptions can
        # quote source-row content verbatim (pandas / pyarrow); without
        # the truncation a single malformed row's value can land in
        # downstream log aggregators.
        error_text = str(exc)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."

        # PII egress guard (dennis sprint-5 BLOCKER): the raw engine error
        # can quote source-row cell values verbatim (see the comment above),
        # so it MUST NOT ride into an outbound notification, which is POSTed
        # to a third-party webhook / Slack / email. Only the exception TYPE
        # name goes on the wire; the raw error_text stays on local stdout /
        # stderr and the --json envelope below where the operator already
        # sees it. Redaction by construction, mirroring the platform's
        # facts-only alert rule (dispatcher.py:137-142).
        notify_results = _dispatch_run_notifications(
            notify_channels,
            notify_on=notify_on.value,
            status="failure",
            config_path=config_str,
            row_count=None,
            started_at=_run_started_at,
            finished_at=datetime.now(timezone.utc),
            error_summary=type(exc).__name__,
            state=state,
        )

        if state.mode is OutputMode.json:
            # R7: the capacity branch ADDS error_kind/code to this SAME
            # envelope -- command/config/mode/error are never dropped, and
            # this is the one emit_json call site for a run-time failure
            # (no parallel emit that would lose the 500-char cap, the
            # notify dispatch above, or quiet/verbose handling below).
            payload = {
                "command": "run",
                "status": "error",
                "config": config_str,
                "mode": yaml_mode,
                "error": error_text,
            }
            if capacity_code is not None:
                payload["error_kind"] = "capacity"
                payload["code"] = capacity_code
            elif native_code is not None:
                payload["error_kind"] = "native"
                payload["code"] = native_code
            elif isinstance(exc, MissingExtraError):
                # A machine-detectable field, not just the
                # `[missing_extra]`-prefixed message text.
                payload["error_kind"] = "missing_extra"
                payload["extra"] = exc.extra
            if notify_channels:
                payload["notify"] = notify_results
            emit_json(state, payload)
        elif state.mode is not OutputMode.quiet:
            # CLI install DX (2026-09-25): error_text is arbitrary exception
            # text, not authored UI copy -- it can legitimately contain `[`
            # (a MissingExtraError's `pip install decoy-cli[cloud]`, a
            # Phase 3.1 native-gate message quoting `decoy-cli[native]` or a
            # companion's own ABI string, or any future message that quotes
            # a list/bracketed value). markup=False so Rich prints it
            # verbatim instead of parsing it as markup and silently
            # dropping an unrecognized tag.
            if capacity_code is not None:
                state.err_console.print(error("capacity:"), error_text, markup=False)
                state.err_console.print(
                    " ",
                    hint("hint:"),
                    "this job needs more memory than this host has; use a larger "
                    "tier or reduce the job.",
                )
            else:
                state.err_console.print(error("error:"), error_text, markup=False)
                state.err_console.print(
                    " ", hint("hint:"), "rerun with --verbose for the full traceback."
                )
        if state.verbose:
            state.err_console.print_exception()
        _finish_record(_record, "error", _exit_code, type(exc).__name__)
        raise typer.Exit(code=_exit_code)

    elapsed = time.perf_counter() - started
    _finish_record(_record, "ok", EXIT_OK)

    # Write evidence manifest if --evidence-out was given. Written for BOTH
    # plain and chunked runs: the input/output fingerprints (the drift-detection
    # core) are always populated. Chunked runs return no ExecutionResult, so
    # row_counts/timings/warnings are empty for them (documented in the flag help).
    if evidence_out is not None and _ev_config_dict is not None:
        from decoy.cli.evidence import build_manifest

        manifest = build_manifest(
            pipeline_path=config,
            config_dict=_ev_config_dict,
            run_result={"row_counts": _ev_row_counts or {}},
            cli_version=_cli_version,
            engine_version=_ev_engine_version or "unknown",
            key_label=key_label,
            timings=_ev_timings,
            engine_warnings=_ev_engine_warnings,
        )
        evidence_out.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
        if state.mode is not OutputMode.json and state.mode is not OutputMode.quiet:
            from decoy.ui.theme import success as _success

            state.console.print(_success("Evidence:"), str(evidence_out))

    notify_results = _dispatch_run_notifications(
        notify_channels,
        notify_on=notify_on.value,
        status="success",
        config_path=config_str,
        row_count=_notify_row_count,
        started_at=_run_started_at,
        finished_at=datetime.now(timezone.utc),
        error_summary=None,
        state=state,
    )

    # S5 enforce mapping (plan P1-2): the engine never fails the job on a
    # hard-failed validator check -- it only stamps `failed_checks`. The CLI
    # maps a non-empty `failed_checks` under --post-validate-enforce to
    # EXIT_FINDINGS, AFTER the requested sections render and the outputs /
    # evidence are already written. --post-validate (without enforce) is
    # warn-only and leaves the exit code at 0.
    _qm = _report_quality_metrics or {}
    _enforce_fires = bool(post_validate_enforce and _qm.get("failed_checks"))

    if state.mode is OutputMode.json:
        payload = {
            "command": "run",
            "status": "ok",
            "config": config_str,
            "mode": yaml_mode,
            "elapsed_s": round(elapsed, 3),
        }
        if notify_channels:
            payload["notify"] = notify_results
        if _native_route is not None:
            payload["native_route"] = {
                "applicable": _native_route.applicable,
                "state": _native_route.state,
                "label": _native_route.label,
            }
        if not chunked:
            payload["native_threads"] = native_threads
        if _record is not None:
            payload["run_id"] = _record.status.run_id
        if _report_flags:
            report: dict = {}
            if explain_plan:
                report["execution_plan"] = _qm.get("execution_plan")
            if fidelity:
                report["fidelity_reports"] = _qm.get("fidelity_reports")
            if post_validation:
                report["failed_checks"] = _qm.get("failed_checks")
                report["quality_summary"] = _qm.get("quality_summary")
                report["post_validation_enforce"] = post_validate_enforce
            payload["report"] = report
        _checks = _data_checks(_qm)
        if _checks is not None:
            payload["data_checks"] = _checks
        emit_json(state, payload)
        if _enforce_fires:
            _finish_record(_record, "ok", EXIT_FINDINGS)
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    _checks = _data_checks(_qm)

    if state.mode is OutputMode.quiet:
        if _checks is not None and _checks.get("quarantine"):
            # Quiet suppresses stdout only; a row-removing quarantine is still
            # reported on stderr so a scripted run never loses rows silently.
            q = _checks["quarantine"]
            state.err_console.print(
                warn("quarantine:"),
                f"{q['total_quarantined']} row(s) routed to {q['output_path']}",
            )
        if _enforce_fires:
            _finish_record(_record, "ok", EXIT_FINDINGS)
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    facts = [
        ("Pipeline", config.name),
        ("Mode", yaml_mode),
        ("Elapsed", f"{elapsed:.2f}s"),
    ]
    if _checks is not None and _checks.get("quarantine"):
        facts.append(("Quarantined", f"{_checks['quarantine']['total_quarantined']} row(s)"))
    if _native_route is not None:
        facts.append(("Route", _native_route.label))
    if not chunked and native_threads > 1:
        facts.append(("Threads", str(native_threads)))
    if _record is not None:
        facts.append(("Run id", _record.status.run_id))
    if notify_channels:
        delivered = sum(1 for r in notify_results if r["delivered"])
        facts.append(("Notify", f"{delivered}/{len(notify_results)} delivered"))

    render_card(
        state,
        command="decoy run",
        facts=facts,
        next_hint=_next_hint_for_run(raw_cfg, mode),
        status="ok",
    )

    if _checks is not None:
        _render_data_checks(state, _checks)

    # S5 report sections (human mode). Rendered below the summary card so the
    # card stays the one-glance result; each is report-only and reads the
    # captured quality metrics.
    if explain_plan:
        _render_execution_route(state, _qm.get("execution_plan"))
    if fidelity:
        _render_fidelity(state, _qm.get("fidelity_reports"))
    if post_validation:
        _render_post_validation(state, _qm, enforce=post_validate_enforce)

    if _enforce_fires:
        _finish_record(_record, "ok", EXIT_FINDINGS)
        raise typer.Exit(code=EXIT_FINDINGS)


def _build_resolver(master_key_hex: str | None, key_label: str | None, raw_cfg: dict | None, state):
    """Construct the engine-facing ``derive_key`` resolver, or None when no
    master key was supplied. Keeps the legacy seeded fallback default so
    runs without a key behave exactly as before.

    ``raw_cfg`` is accepted (and unused) for call-site symmetry with the
    other pre-flight helpers that share the one parsed YAML dict; it used
    to feed a top-level YAML ``key_label:`` reader. This function runs
    early (the run() body calls it ~L307), BEFORE ``PipelineConfig
    .model_validate`` (~L371), so that reader could observe a top-level
    ``key_label:`` value -- but model_validate then runs on the same raw
    dict and PipelineConfig's ``extra="forbid"`` rejects the unknown field,
    so a config carrying it could never reach a successful run regardless
    of what the reader returned. The reader was therefore dead and
    misleading; it is removed. ``--key-label`` is the only live source
    (doc/config mismatch fix, see `decoy explain keys`).
    """
    if not master_key_hex:
        return None

    raw = master_key_hex.strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    try:
        master = bytes.fromhex(raw)
    except (ValueError, binascii.Error) as exc:
        raise typer.BadParameter(
            f"--master-key must be valid hex ({exc}). Generate one via: "
            "python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if len(master) != 32:
        raise typer.BadParameter(f"--master-key must decode to 32 bytes (got {len(master)}).")

    if not key_label:
        raise typer.BadParameter(
            "--master-key requires a --key-label. Pick a stable namespace "
            "string like 'customers_q4'."
        )

    from decoy_engine import make_key_resolver

    return make_key_resolver(master, key_label)


def _detect_mode(raw_cfg: dict | None) -> str | None:
    """Infer mode from the YAML's tables, or return None if not determinable.

    FC-1 (2026-06-02) dropped the top-level `mode:` field; the engine now
    infers per-table kind from `columns` (mask) vs `generate_columns`
    (generate) presence. This helper picks one label for the spinner / the
    JSON envelope's `mode` field: returns "generate" iff EVERY table is
    generate-kind; "mask" iff at least one mask-kind table is present
    (mixed configs label as "mask" because the mask back-half is the
    workflow that touches the operator's source data). The choke-point
    validator still rejects malformed configs.
    """
    if not isinstance(raw_cfg, dict):
        return None
    tables = raw_cfg.get("tables") or []
    if not isinstance(tables, list):
        return None
    has_mask = any(isinstance(t, dict) and t.get("columns") for t in tables)
    has_gen = any(isinstance(t, dict) and t.get("generate_columns") for t in tables)
    if has_mask:
        return "mask"
    if has_gen:
        return "generate"
    return None


def _next_hint_for_run(raw_cfg: dict | None, mode: "Mode") -> str | None:
    """Best-effort follow-up hint based on the YAML's output path."""
    try:
        out = raw_cfg.get("output", {}).get("path") if isinstance(raw_cfg, dict) else None
        if out:
            return f"head {out}"
    except Exception:
        pass
    return None


def _render_execution_route(state, execution_plan: dict | None) -> None:
    """Render the EXECUTION ROUTE decision (--explain-plan).

    `execution_plan` is `quality_metrics["execution_plan"]` =
    `{mode, reason, rejections}`: which run lane the engine chose (sequential /
    full_frame / out_of_core) and why. This is deliberately NOT the per-column
    masking rationale `validate compile --explain` renders pre-run (plan P1-1) --
    a different payload, so a small dedicated renderer rather than reusing
    compile_explain's column table. `rejections` maps each lane the engine
    DECLINED to the reason it was declined.
    """
    state.console.print()
    state.console.print(accent("Execution route"))
    if not execution_plan:
        # explain_plan was requested but the engine stamped nothing (e.g. a path
        # that produced no decision). Say so rather than render an empty table.
        state.console.print(
            hint("  "), "no execution-route decision was recorded for this run."
        )
        return
    state.console.print("  Mode:", code(str(execution_plan.get("mode", "?"))))
    state.console.print("  Reason:", str(execution_plan.get("reason", "?")))
    rejections = execution_plan.get("rejections") or {}
    if rejections:
        tbl = make_table("Lane declined", "Why")
        for lane, why in rejections.items():
            tbl.add_row(str(lane), str(why))
        state.console.print(tbl)
    state.console.print(
        hint("  Note:"),
        "this is the execution ROUTE decision, not the per-column masking "
        "rationale. For that, run",
        code("decoy validate compile --explain"),
        "before the run.",
    )


def _render_fidelity(state, fidelity_reports: dict | None) -> None:
    """Render the QUICK inline marginal-fidelity check (--fidelity).

    `fidelity_reports` is `quality_metrics["fidelity_reports"]`, a per-mask-table
    `quality-report/v1` block. This is a quick inline glance (letter grade +
    overall score, marginal-only); it NEVER fails the run. The fuller post-hoc
    grade is `decoy report fidelity` (plan P2-4).
    """
    state.console.print()
    state.console.print(accent("Fidelity (quick inline check)"))
    if not fidelity_reports:
        state.console.print(
            hint("  "), "no mask-table fidelity report was produced for this run."
        )
        return
    tbl = make_table("Table", "Grade", "Overall score")
    for table_name, rep in fidelity_reports.items():
        rep = rep or {}
        score = rep.get("overall_score")
        tbl.add_row(
            str(table_name),
            str(rep.get("grade", "?")),
            "n/a" if score is None else f"{score:.3f}",
        )
    state.console.print(tbl)
    state.console.print(
        hint("  Note:"),
        "a quick marginal check; a low grade does not fail the run. For the "
        "fuller post-hoc grade, run",
        code("decoy report fidelity"),
        ".",
    )


def _data_checks(qm: dict) -> dict | None:
    """Fold the engine's in-run data-check evidence into one envelope block.

    Reads `quality_metrics["validation"]["validators"]` (the `validators:`
    block's `ValidationReport`), `["quarantine"]` (the `QuarantineSummary`,
    present only when rows were removed), `["row_errors"]` (per
    table.column[trigger] counts) and `["row_error_summary_by_table"]`. All
    four are counts and identifiers only, never cell values. Returns None when
    the run produced none of them, so a plain run's output is unchanged.
    """
    out: dict = {}
    validation = (qm.get("validation") or {}).get("validators")
    if isinstance(validation, dict):
        per_validator: dict[str, int] = {}
        for finding in validation.get("findings") or ():
            key = str((finding or {}).get("validator", "?"))
            per_validator[key] = per_validator.get(key, 0) + len(
                (finding or {}).get("failing_row_indices") or ()
            )
        out["validators"] = {
            "run": list(validation.get("validators_run") or ()),
            "passed": bool(validation.get("passed")),
            "findings": len(validation.get("findings") or ()),
            "failing_rows_by_validator": per_validator,
        }
    quarantine = qm.get("quarantine")
    if isinstance(quarantine, dict) and quarantine.get("total_quarantined"):
        out["quarantine"] = {
            "output_path": quarantine.get("output_path"),
            "total_quarantined": int(quarantine.get("total_quarantined") or 0),
            "counts_by_trigger": dict(quarantine.get("counts_by_trigger") or {}),
        }
    row_errors = qm.get("row_errors")
    if isinstance(row_errors, dict) and row_errors:
        out["row_errors"] = dict(row_errors)
    by_table = qm.get("row_error_summary_by_table")
    if isinstance(by_table, dict) and by_table:
        out["row_error_summary_by_table"] = by_table
    return out or None


def _render_data_checks(state, checks: dict) -> None:
    """Human rendering of `_data_checks`: what the validators found, how many
    rows quarantine removed and where they went, and per-column row-error
    counts. Identifiers and counts only."""
    state.console.print()
    state.console.print(accent("Data checks"))
    validators = checks.get("validators")
    if validators:
        ran = ", ".join(validators["run"]) or "none"
        if validators["passed"]:
            state.console.print(success(f"  Validators passed ({ran})."))
        else:
            tbl = make_table("Validator", "Failing rows")
            for name, count in sorted(validators["failing_rows_by_validator"].items()):
                tbl.add_row(name, str(count))
            state.console.print(tbl)
    quarantine = checks.get("quarantine")
    if quarantine:
        state.console.print(
            warn("  Quarantined:"),
            f"{quarantine['total_quarantined']} row(s) removed from the written output and "
            f"routed to {quarantine['output_path']}",
        )
        for trigger, count in sorted(quarantine["counts_by_trigger"].items()):
            state.console.print(hint("    "), f"{trigger}: {count}")
    row_errors = checks.get("row_errors")
    if row_errors:
        tbl = make_table("Column [trigger]", "Rows")
        for key, count in sorted(row_errors.items()):
            tbl.add_row(key, str(count))
        state.console.print(tbl)


def _render_post_validation(state, qm: dict, *, enforce: bool) -> None:
    """Render the post-execution validator results (--post-validate[-enforce]).

    Reads `quality_metrics["failed_checks"]` (a list of `{code, message}`) and
    `["quality_summary"]` (the manifest block). Warn-only by default; under
    --post-validate-enforce a non-empty `failed_checks` maps to EXIT_FINDINGS in
    the caller (the engine never fails the job -- plan P1-2).
    """
    state.console.print()
    state.console.print(accent("Post-validation"))
    failed = qm.get("failed_checks") or []
    summary = qm.get("quality_summary")
    if summary is None:
        state.console.print(
            hint("  "), "no post-validation summary was produced for this run."
        )
        return
    if not failed:
        state.console.print(success("  All post-validation checks passed."))
        return
    tbl = make_table("Failed check", "Detail")
    for item in failed:
        item = item or {}
        tbl.add_row(str(item.get("code", "?")), str(item.get("message", "")))
    state.console.print(tbl)
    if enforce:
        state.console.print(
            warn("  enforce:"),
            f"{len(failed)} hard-failed check(s); outputs were written, exiting "
            "with findings (code 4).",
        )
    else:
        state.console.print(
            hint("  Note:"),
            f"{len(failed)} hard-failed check(s) reported; warn-only, the run "
            "still exits 0. Use",
            code("--post-validate-enforce"),
            "to exit with findings.",
        )


def _run_chunked_mask(
    config_dict: dict,
    base_dir: Path,
    chunk_size: int,
    vault_writer=None,
) -> str:
    """WS4 chunked mask path: stream each mask table's source through
    `decoy_engine.run_mask_pipeline_chunked`, writing output per chunk.

    Returns the adapter label ("pandas"): the chunked path has no
    `ExecutionResult` to read a route from, so the caller's native-route
    indicator (Phase 3.1) builds its "Route: pandas chunked stream" label
    from this.

    The engine's `check_chunked_compatibility` rejects anything that is
    not value-keyed (PlanCompileError -> EXIT_USAGE via the H10 typed
    dispatch), so a chunked run that starts is guaranteed byte-identical
    to a plain run of the same config for CSV targets. Parquet targets
    are VALUE-equal to a plain run; their file bytes are stable for a
    fixed (chunk_size, pyarrow version) but not across chunk sizes,
    because each chunk writes one row group.

    Formats: CSV and parquet, on either side independently. The source
    reader follows the declared source `format`; the writer follows the
    target path suffix. Parquet reads stream via ParquetFile.iter_batches; CSV reads keep
    the dtype=str contract of the plain path, so a csv -> parquet run
    produces an all-string schema.

    The engine's pandas adapter is the only chunked adapter."""
    _require_local_io_endpoints(config_dict)

    from decoy_engine import __version__ as engine_version
    from decoy_engine import run_mask_pipeline_chunked

    resolved_substrate = "pandas"

    sources = config_dict.get("sources") or {}
    targets = config_dict.get("targets") or {}
    for table_entry in config_dict.get("tables") or []:
        if not isinstance(table_entry, dict) or not table_entry.get("columns"):
            continue
        name = table_entry.get("name")
        assert isinstance(name, str)  # pydantic guarantees a str table name
        src_spec = sources.get(name) if isinstance(sources, dict) else None
        tgt_spec = targets.get(name) if isinstance(targets, dict) else None
        if not isinstance(src_spec, dict) or not isinstance(src_spec.get("path"), str):
            continue
        src_path = _resolve_path(src_spec["path"], base_dir)
        if not isinstance(tgt_spec, dict) or not isinstance(tgt_spec.get("path"), str):
            continue
        out_path = _resolve_path(tgt_spec["path"], base_dir)

        masked_iter = _count_chunk_rows(
            name,
            run_mask_pipeline_chunked(
                config_dict,
                iter_source_chunks(name, src_spec, base_dir, chunk_size),
                table=name,
                engine_version=engine_version,
                vault_writer=vault_writer,
            ),
        )
        _write_chunked_output(
            masked_iter, out_path, src_path, src_is_parquet=src_spec.get("format") == "parquet"
        )

    return resolved_substrate


def _write_chunked_output(
    masked_iter, out_path: Path, src_path: Path, *, src_is_parquet: bool
) -> None:
    """Stream masked chunks to `out_path`, format picked by its suffix."""
    if out_path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        writer = None
        try:
            for masked in masked_iter:
                if writer is None:
                    writer = pq.ParquetWriter(str(out_path), masked.schema)
                writer.write_table(masked)
            if writer is None and src_is_parquet:
                # Empty parquet source: emit a valid zero-row file with the
                # source schema, matching what a plain run writes. (An empty
                # CSV source writes nothing, same as the CSV target path.)
                schema = pq.ParquetFile(str(src_path)).schema_arrow
                writer = pq.ParquetWriter(str(out_path), schema)
        finally:
            if writer is not None:
                writer.close()
        return
    first = True
    for masked in masked_iter:
        masked.to_pandas().to_csv(out_path, index=False, header=first, mode="w" if first else "a")
        first = False


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    """Resolve a YAML path against the config's directory.

    Mirrors `decoy validate compile`'s source-loading behavior: relative paths
    in the YAML resolve relative to the YAML file's directory, not the CWD.
    Absolute paths pass through unchanged.
    """
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _require_local_io_endpoints(config_dict: dict) -> None:
    """Refuse a config whose `sources`/`targets` declare an s3 or gcs
    endpoint before any data is read or the engine is invoked.

    The helpers below (`_load_sources_from_config`, `_write_mask_outputs`,
    `_run_chunked_mask`) only read and write local files; they would skip a
    cloud entry and report success with that table's output dropped. They
    are shared by `decoy run` and the `decoy.mask()` library API, so the
    refusal lives here, at the I/O layer every entry point goes through,
    rather than in one command's body where another caller could bypass it
    (a cloud source would then fail late, as an ImportError from the
    engine's profiler when [cloud] is absent). Each helper calls this
    itself, so a helper reached without the others still refuses.

    `check_cloud_endpoints_supported` raises first and unconditionally,
    since installing [cloud] adds the SDK but not a cloud I/O path here.
    `check_cloud_endpoints` (SDK presence) stays second so the install hint
    still applies if cloud I/O is ever wired into these helpers.
    """
    check_cloud_endpoints_supported(config_dict)
    check_cloud_endpoints(config_dict)


def _load_sources_from_config(config_dict: dict, base_dir: Path) -> dict:
    """Read each `sources[table]` into a `dict[str, pa.Table]`.

    Reads each source by its declared `format` (csv, parquet, fixed_width).
    Sources without a `path` field are skipped (the engine treats absent tables as empty, but
    the mask spine will error on a missing source if the plan needs it;
    leave that error to the engine layer).

    Checks targets as well as sources (via `_require_local_io_endpoints`):
    this is the first I/O step on every non-chunked path, so an s3/gcs
    target is refused here, before the engine runs, not after the masking
    work is done and `_write_mask_outputs` finds nowhere to put it.
    """
    _require_local_io_endpoints(config_dict)

    import pyarrow as pa

    out: dict[str, pa.Table] = {}
    sources = config_dict.get("sources") or {}
    if not isinstance(sources, dict):
        return out
    for table_name, src in sources.items():
        if not _native_gate.source_is_materialized(src):
            continue
        out[table_name] = read_source(table_name, src, base_dir)
    return out


def _write_mask_outputs(config_dict: dict, result, base_dir: Path) -> None:
    """Write each declared target from the V2 ExecutionResult.

    CLI.3 commit 2 (2026-06-02) fix: the V2 ExecutionResult exposes
    masked tables on `outputs` (dict[table_name -> pa.Table]), not
    `tables`. The V2 `targets:` block is a dict keyed by table name,
    not a list of `{table, path}` entries. Pre-fix the CLI silently
    skipped the writer (no errors, no output file), surfaced by the
    demo + test_output_modes smoke runs.

    The pandas adapter returns masked tables in-memory; the polars
    adapter writes them via its own target-writer. CLI.1 bridges the
    pandas path with this helper. Format inferred from the path
    extension (csv or parquet).

    Refuses s3/gcs targets rather than skipping them, for a caller that
    writes without having gone through `_load_sources_from_config`.
    """
    _require_local_io_endpoints(config_dict)

    targets = config_dict.get("targets") or {}
    if not isinstance(targets, dict):
        return
    outputs = getattr(result, "outputs", None)
    if not isinstance(outputs, dict):
        return
    for table_name, entry in targets.items():
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        table = outputs.get(table_name)
        if table is None:
            continue
        path = _resolve_path(raw_path, base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_target_table(table, entry, path)


def _write_target_table(table, entry: dict, path: Path) -> None:
    """Write one masked table per the target's DECLARED `format`.

    The schema requires `format` on every file target and a `layout` on a
    fixed-width one, so the declared format is the only thing consulted;
    the path suffix is a fallback for a hand-built dict with no `format`.
    Before this dispatch a `format: fixed_width` target fell through the
    suffix check and was silently written as CSV.
    """
    fmt = entry.get("format")
    if fmt is None:
        fmt = "parquet" if path.suffix.lower() == ".parquet" else "csv"
    if fmt == "parquet":
        import pyarrow.parquet as pq

        pq.write_table(table, str(path))
    elif fmt == "fixed_width":
        from decoy_engine import write_fixed_width

        write_fixed_width(_fixed_width_frame(table, entry["layout"]), entry["layout"], path)
    else:
        table.to_pandas().to_csv(path, index=False)


def _fixed_width_frame(table, layout: dict):
    """Arrow -> pandas without widening integers to float.

    `to_pandas()` turns a null-bearing Arrow int column into float64, which the
    engine's fixed-width writer rejects (fail-closed, never a silent round).
    Map Arrow integer types to pandas nullable integers instead; an `int`
    layout column that still arrives as an all-integral float (a masked
    column the engine returned as float) is narrowed the same way. Anything
    else is left for the writer to refuse.
    """
    import pandas as pd
    import pyarrow as pa

    nullable = {
        pa.int8(): pd.Int8Dtype(), pa.int16(): pd.Int16Dtype(),
        pa.int32(): pd.Int32Dtype(), pa.int64(): pd.Int64Dtype(),
        pa.uint8(): pd.UInt8Dtype(), pa.uint16(): pd.UInt16Dtype(),
        pa.uint32(): pd.UInt32Dtype(), pa.uint64(): pd.UInt64Dtype(),
    }
    frame = table.to_pandas(types_mapper=nullable.get)
    for column in layout.get("columns") or []:
        name = column.get("name") if isinstance(column, dict) else None
        if column.get("type") != "int" or name not in frame.columns:
            continue
        series = frame[name]
        if pd.api.types.is_float_dtype(series.dtype):
            present = series.dropna()
            if (present == present.round()).all():
                frame[name] = series.astype("Int64")
    return frame


def _dispatch_run_notifications(
    channels: list,
    *,
    notify_on: str,
    status: str,
    config_path: str,
    row_count: int | None,
    started_at,
    finished_at,
    error_summary: str | None,
    state,
) -> list[dict]:
    """Best-effort post-run notification fan-out (N3).

    Called AFTER the run reaches its terminal state (both the success tail
    and the failure tail call this). Never raises and never changes the
    run's own exit code: a channel failure only logs a stderr warning and
    is reflected in the returned per-channel results (D2 -- "alerting must
    never take a job down", mirrors dispatcher.py:14-17). Returns `[]`
    when no --notify channels were configured, or when --notify-on filters
    out this outcome.
    """
    if not channels:
        return []

    from decoy.notify import SmtpConfig, build_run_event, dispatch, should_notify

    if not should_notify(notify_on, status):
        return []

    try:
        event = build_run_event(
            status=status,
            config_path=config_path,
            row_count=row_count,
            started_at=started_at,
            finished_at=finished_at,
            error_summary=error_summary,
        )
        webhook_secret = os.environ.get("DECOY_NOTIFY_WEBHOOK_SECRET")
        smtp = SmtpConfig(
            host=os.environ.get("DECOY_NOTIFY_SMTP_HOST", ""),
            port=int(os.environ.get("DECOY_NOTIFY_SMTP_PORT") or 587),
            user=os.environ.get("DECOY_NOTIFY_SMTP_USER") or None,
            password=os.environ.get("DECOY_NOTIFY_SMTP_PASS") or None,
            from_addr=os.environ.get("DECOY_NOTIFY_SMTP_FROM") or None,
        )
        results = dispatch(event, channels, webhook_secret=webhook_secret, smtp=smtp)
        if state.mode is not OutputMode.quiet:
            for r in results:
                if not r.delivered:
                    detail = f": {r.detail}" if r.detail else "."
                    state.err_console.print(
                        warn("warning:"),
                        f"notify {r.kind} to {r.target_host} did not deliver{detail}",
                    )
        return [
            {"kind": r.kind, "delivered": r.delivered, "target_host": r.target_host}
            for r in results
        ]
    except Exception as exc:  # notify must never take the run down (D2)
        if state.mode is not OutputMode.quiet:
            state.err_console.print(warn("warning:"), f"notify dispatch failed: {exc}")
        return []


# The epilog is wired by __main__ at command registration time; the
# docstring on `run` stays as the help body.
RUN_EPILOG = _RUN_EPILOG


# ---------------------------------------------------------------------------
# Local run records + progress binding (parity C4)
# ---------------------------------------------------------------------------


def _open_run_record(state, config: Path, yaml_mode: str, run_id: str | None):
    """Create this run's record under `$DECOY_HOME/runs`; a record failure never
    stops the run (warn and continue without one)."""
    from decoy import runs as _runs

    try:
        record = _runs.RunRecord.create(config=str(config), mode=yaml_mode, run_id=run_id)
    except FileExistsError:
        msg = f"run id {run_id!r} already exists under {_runs.runs_root()}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "run", "status": "error", "config": str(config), "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)
    except OSError as exc:
        if state.mode is not OutputMode.quiet:
            state.err_console.print(
                warn("warning:"), f"could not create a run record ({type(exc).__name__}); continuing"
            )
        return None
    try:
        _runs.prune()
    except OSError:
        pass
    return record


def _finish_record(record, state_name: str, exit_code: int | None, error_class: str | None = None) -> None:
    """Mark the record terminal once; a later call may only fill in an exit code
    the first call did not know yet (the error handler learns the code after it
    has classified the exception)."""
    if record is None:
        return
    try:
        if record.status.state in ("ok", "error", "interrupted"):
            if record.status.exit_code is None and exit_code is not None:
                record.status.exit_code = exit_code
                record.save()
            return
        record.finish(state_name, exit_code=exit_code, error_class=error_class)
    except OSError:
        pass


class _LiveSink:
    """Map engine events onto the live status line (identifiers and counts only)."""

    def __init__(self, live) -> None:
        self._live = live

    def on_event(self, event) -> None:
        kind = getattr(event, "kind", None)
        if kind == "phase" and event.status == "start":
            where = f" {event.table}" if event.table else ""
            self._live.update(f"[{event.name}{where}]")
        elif kind == "rate":
            self._live.update(f"[{event.table}] {event.rows_done:,} rows ({event.rows_per_sec:,.0f} rows/s)")
        elif kind == "route":
            lane = f"/{event.lane}" if event.lane else ""
            self._live.update(f"[route {event.route}{lane}]")


@contextmanager
def _progress_binding(*, record, live, progress: str, progress_file: Path | None, config_label: str):
    """Bind the run's progress sinks (record, JSONL stream, live line) as the
    engine's active progress channel, and keep the record's heartbeat alive.
    An engine that predates `decoy_engine.progress` gets no binding and the run
    behaves as before."""
    from decoy import runs as _runs

    try:
        from decoy_engine.progress import use_progress
    except ImportError:  # pragma: no cover - older engine
        yield
        return
    sinks: list = []
    handles: list = []
    rid = record.status.run_id if record is not None else None
    if record is not None:
        sinks.append(_runs.RunRecordSink(record))
    if progress == "jsonl":
        sinks.append(_runs.JsonlStreamSink(sys.stderr, run_id=rid, config=config_label))
    if progress_file is not None:
        fh = open(progress_file, "a", encoding="utf-8")  # noqa: SIM115 - closed in finally
        handles.append(fh)
        sinks.append(_runs.JsonlStreamSink(fh, run_id=rid, config=config_label))
    if progress == "auto":
        sinks.append(_LiveSink(live))
    sink = _runs.FanoutSink(sinks) if sinks else None
    try:
        if record is not None:
            with _runs.Heartbeat(record), use_progress(sink, interval_s=0.5):
                yield
        else:
            with use_progress(sink, interval_s=0.5):
                yield
    finally:
        for fh in handles:
            fh.close()


def _count_chunk_rows(table: str, chunks):
    """Account the legacy chunked lane's yielded chunks on the active progress
    channel (the lane itself predates the progress contract)."""
    try:
        from decoy_engine.progress import get_active_channel
    except ImportError:  # pragma: no cover - older engine
        return chunks
    return get_active_channel().count_rows(table, chunks)


# ---------------------------------------------------------------------------
# Batch mode: several configs, --jobs at a time (parity C4c)
# ---------------------------------------------------------------------------

_BATCH_PER_RUN_ONLY = ("vault", "evidence_out", "progress_file")


def _batch_child_argv(config: Path, child_run_id: str, options: dict) -> list[str]:
    """`python -m decoy run <config> --json --progress none --run-id <id>` plus the
    pass-through flags; each child is a normal single run in its own process."""
    argv = [sys.executable, "-m", "decoy", "run", str(config), "--json", "--progress", "none",
            "--run-id", child_run_id, "--mode", options["mode"].value]
    if options["master_key"]:
        argv += ["--master-key", options["master_key"]]
    if options["mask_secret"]:
        argv += ["--mask-secret", options["mask_secret"]]
    if options["key_label"]:
        argv += ["--key-label", options["key_label"]]
    if options["chunked"]:
        argv += ["--chunked", "--chunk-size", str(options["chunk_size"])]
    if options["threads"] is not None:
        argv += ["--threads", str(options["threads"])]
    for spec in options["notify"] or ():
        argv += ["--notify", spec]
    if options["notify"]:
        argv += ["--notify-on", options["notify_on"].value]
    for flag in ("native", "no_native", "explain_plan", "fidelity", "post_validate", "post_validate_enforce", "no_record"):
        if options[flag]:
            argv.append("--" + flag.replace("_", "-"))
    return argv


def _batch_target_paths(config: Path) -> set[str]:
    raw = _load_raw_config(config) or {}
    targets = raw.get("targets") or {}
    out: set[str] = set()
    if isinstance(targets, dict):
        for entry in targets.values():
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                out.add(str(_resolve_path(entry["path"], config.parent)))
    return out


def _run_batch(state, configs: list[Path], *, jobs: int, watch: bool, run_id: str | None, options: dict) -> int:
    """Run every config as its own child process, `jobs` at a time. The exit
    code is the worst child's. Two configs that declare the same target path are
    refused up front (they would race on the file)."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    from decoy import runs as _runs

    def usage(msg: str) -> int:
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "run", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        return EXIT_USAGE

    for name in _BATCH_PER_RUN_ONLY:
        if options.get(name):
            return usage(f"--{name.replace('_', '-')} names one file and cannot be shared by a batch; run those configs one at a time")
    seen: dict[str, Path] = {}
    for cfg in configs:
        for path in _batch_target_paths(cfg):
            if path in seen and seen[path] != cfg:
                return usage(f"{cfg} and {seen[path]} both write {path}; a batch cannot run two configs with the same target")
            seen[path] = cfg

    batch_id = run_id or _runs.new_run_id()
    children = [(cfg, f"{batch_id}-{i + 1}") for i, cfg in enumerate(configs)]

    def run_child(item: tuple[Path, str]) -> dict:
        cfg, child_id = item
        started = time.perf_counter()
        proc = subprocess.run(_batch_child_argv(cfg, child_id, options), capture_output=True, text=True)
        envelope: dict | None = None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith("{"):
                try:
                    envelope = _json.loads(line)
                except ValueError:
                    envelope = None
                break
        return {
            "config": str(cfg),
            "run_id": child_id,
            "exit_code": proc.returncode,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "result": envelope,
            "stderr_tail": proc.stderr.strip().splitlines()[-3:] if proc.returncode else [],
        }

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_child, item) for item in children]
        if watch and state.mode is OutputMode.default and state.err_console.is_terminal:
            _watch_batch(state, [cid for _, cid in children], futures)
        results = [f.result() for f in futures]

    worst = max((r["exit_code"] for r in results), default=EXIT_OK)
    if state.mode is OutputMode.json:
        emit_json(state, {
            "command": "run",
            "status": "ok" if worst == EXIT_OK else "error",
            "batch_id": batch_id,
            "jobs": jobs,
            "exit_code": worst,
            "runs": results,
        })
        return worst
    if state.mode is OutputMode.quiet:
        return worst
    tbl = make_table("Config", "Run id", "Exit", "Elapsed")
    for r in results:
        tbl.add_row(r["config"], r["run_id"], str(r["exit_code"]), f"{r['elapsed_s']:.2f}s")
    render_card(
        state,
        command="decoy run (batch)",
        facts=[("Configs", str(len(results))), ("Jobs", str(jobs)), ("Batch id", batch_id),
               ("Failed", str(sum(1 for r in results if r["exit_code"])))],
        next_hint=f"decoy status --json   # records {batch_id}-1 .. {batch_id}-{len(results)}",
        status="ok" if worst == EXIT_OK else "error",
    )
    state.console.print(tbl)
    for r in results:
        for line in r["stderr_tail"]:
            state.err_console.print(error(f"[{r['run_id']}]"), line, markup=False)
    return worst


def _watch_batch(state, run_ids: list[str], futures) -> None:
    """Re-render the batch's run records every second until every child exits."""
    from rich.live import Live

    from decoy import runs as _runs
    from decoy.cli.status import rows_table, run_row

    def snapshot():
        rows = []
        for rid in run_ids:
            rec = _runs.find_run(rid)
            rows.append(run_row(rec) if rec is not None else {"run_id": rid, "state": "pending", "phase": None,
                        "table": None, "rows_done": 0, "rows_per_sec": None, "mode": "", "config": ""})
        return rows_table(rows)

    try:
        with Live(snapshot(), console=state.err_console, refresh_per_second=4, transient=True) as live:
            while not all(f.done() for f in futures):
                time.sleep(1.0)
                live.update(snapshot())
    except KeyboardInterrupt:
        raise
