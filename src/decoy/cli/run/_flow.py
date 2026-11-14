"""The skeleton of a `decoy run`: the order of the phases, the error arm and the cleanup."""

import contextlib
import time
from datetime import datetime, timezone

import typer

from decoy.cli.io import LayoutError, mint_invocation_id, open_out_dir
from decoy.cli.project import only_pipeline, run_all
from decoy.cli.run import _errors, _evidence, _execute, _prepare, _render
from decoy.cli.run._context import RunContext
from decoy.cli.run._notify import (
    _begin_trace,
    _dispatch_run_notifications,
    _end_trace,
    _start_telemetry,
    parse_channels,
)
from decoy.cli.run._prepare import (
    _build_resolver,
    _detect_mode,
    _has_kind,
    _load_raw_config,
    _refuse_fidelity_without_mask,
)
from decoy.ui.progress import spinner

# How each `run` option reaches an `--all` child. Every parameter of `run()` is in exactly one of
# these tables or in `NOT_FORWARDED`; `tests/e2e/project_layout/test_run_all.py` reads the
# signature and fails for a new option that is in none. Entries are (flag, RunContext field).
FORWARD_ENUMS = (("--mode", "mode"), ("--notify-on", "notify_on"))  # always sent, by value
FORWARD_VALUES = (  # sent when set
    ("--mask-secret", "mask_secret"),
    ("--chunk-size", "chunk_size"),
    ("--max-memory", "max_memory"),
    ("--threads", "threads"),
    ("--key-label", "key_label"),
    ("--otel-endpoint", "otel_endpoint"),
    ("--rows", "rows"),
)
FORWARD_REPEATED = (("--notify", "notify"), ("--duckdb-source", "duckdb_source"))
FORWARD_SWITCHES = (  # sent when on
    ("-v", "verbose"),
    ("--chunked", "chunked"),
    ("--native", "native"),
    ("--no-native", "no_native"),
    ("--explain-plan", "explain_plan"),
    ("--fidelity", "fidelity"),
    ("--post-validate", "post_validate"),
    ("--post-validate-enforce", "post_validate_enforce"),
)
# Each names one file, so `--all` would write it once per pipeline: refused with exit 1.
REFUSED_WITH_ALL = (
    ("--evidence-out", "evidence_out"),
    ("--vault", "vault"),
    ("--out-dir", "out_dir"),
)
# Handled apart from forwarding: `ctx`, `config` and `all_` pick the pipelines; the child always
# gets `--json`, so `json_` and `quiet` (mutually exclusive with it) are not passed; the master
# key goes by environment, never argv.
NOT_FORWARDED = ("ctx", "config", "all_", "json_", "quiet", "master_key")


def _child_flags(ctx: RunContext) -> list[str]:
    """The options each `--all` child gets, from the tables above."""
    flags: list[str] = []
    for flag, field in FORWARD_ENUMS:
        flags += [flag, getattr(ctx, field).value]
    for flag, field in FORWARD_VALUES:
        if getattr(ctx, field) is not None:
            flags += [flag, str(getattr(ctx, field))]
    for flag, field in FORWARD_REPEATED:
        for value in getattr(ctx, field):
            flags += [flag, value]
    return flags + [flag for flag, field in FORWARD_SWITCHES if getattr(ctx, field)]


def _bind_pipeline(ctx: RunContext) -> None:
    """Fan out for `--all`, else settle which YAML this process runs (given, or the only one)."""
    if ctx.all_:
        refused = [flag for flag, field in REFUSED_WITH_ALL if getattr(ctx, field) is not None]
        key = {"DECOY_MASTER_KEY": ctx.master_key} if ctx.master_key is not None else {}
        run_all(
            ctx.state,
            ctx.cli,
            named=ctx.named,
            refused=refused,
            flags=_child_flags(ctx),
            env=key,
        )
    ref = ctx.pipeline if ctx.pipeline is not None else only_pipeline(ctx.state, ctx.cli)
    ctx.config, ctx.given_as = ref.yaml, ref.given_as


def execute(ctx: RunContext) -> None:
    """Run the phases in order. Everything after the `try` runs only on success."""
    _bind_pipeline(ctx)
    ctx.invocation_id = mint_invocation_id()
    ctx.config_str = str(ctx.config)

    parse_channels(ctx)

    ctx.raw, ctx.saved_findings, ctx.config_read_error = _load_raw_config(ctx.config)
    ctx.raw_cfg = ctx.raw if isinstance(ctx.raw, dict) else None
    ctx.yaml_mode = _detect_mode(ctx.raw_cfg) or ctx.mode.value

    if ctx.rows is not None:
        _prepare.refuse_preview(ctx)

    ctx.resolver = _build_resolver(ctx.master_key, ctx.key_label, ctx.raw_cfg, ctx.state)
    if ctx.fidelity and ctx.raw_cfg is not None and not _has_kind(ctx.raw_cfg, "columns"):
        _refuse_fidelity_without_mask(ctx.state, ctx.config_str, ctx.raw_cfg)

    ctx.post_validation = ctx.post_validate or ctx.post_validate_enforce
    ctx._report_flags = ctx.explain_plan or ctx.fidelity or ctx.post_validation

    ctx._run_started_at = datetime.now(timezone.utc)
    ctx.started = time.perf_counter()
    finished = False
    _otel = _trace = _failed_with = None
    try:
        # F30: refuse a bad telemetry setting before any work.
        _otel = _start_telemetry(ctx.otel_endpoint, ctx.state)
        _trace = _begin_trace(_otel)
        with spinner(ctx.state, f"Running {ctx.yaml_mode}..."), contextlib.ExitStack() as _scopes:
            if _trace is not None:
                # One binding reaches the full-frame, `--chunked` and preview calls alike;
                # the engine's own entries leave an outer binding in place.
                from decoy_engine.progress import use_progress

                _scopes.enter_context(use_progress(_trace.recorder))
            if ctx.rows is None and ctx.out_dir is not None:
                failed = False
                try:
                    ctx.layout = open_out_dir(ctx.out_dir)
                except LayoutError:
                    failed = True
                if failed:
                    raise _errors.OutDirUsageError()
            if ctx.rows is None:
                _prepare.prepare(ctx, _scopes)
                _execute.execute(ctx)
            else:
                _prepare.prepare_preview(ctx)
                _execute.execute_preview(ctx)
        finished = True
    except typer.Exit:
        # An inner typer.Exit already set its exit code; keep it out of the catch-all below.
        raise
    except Exception as exc:
        _failed_with = type(exc).__name__
        _errors.fail(ctx, exc)
    finally:
        # A run that failed before writing anything leaves no empty run folder.
        if not finished and ctx.layout is not None:
            ctx.layout.abandon()
        # Tear down any --duckdb-source Parquet snapshots. Runs on success
        # (before the summary tail) and on every error path. By here the run
        # has already consumed the staged Parquet, and --evidence-out is
        # refused alongside --duckdb-source, so nothing downstream reads it.
        if ctx._duckdb_tmpdir is not None:
            import shutil

            shutil.rmtree(ctx._duckdb_tmpdir, ignore_errors=True)
        # Last, so a Ctrl-C during the bounded flush cannot skip the cleanup above. The exit
        # code is decided by now (`fail` raised its typer.Exit above).
        _end_trace(_otel, _trace, ok=finished, error_class=_failed_with)

    ctx.elapsed = time.perf_counter() - ctx.started

    if ctx.rows is not None:
        # A preview writes no evidence and sends no notification.
        _render.finish_preview(ctx)
        return

    _evidence.write_evidence(ctx)
    _render.commit_latest(ctx)

    ctx.notify_results = _dispatch_run_notifications(
        ctx.notify_channels,
        notify_on=ctx.notify_on.value,
        status="success",
        config_path=ctx.config_str,
        row_count=ctx._notify_row_count,
        started_at=ctx._run_started_at,
        finished_at=datetime.now(timezone.utc),
        error_summary=None,
        state=ctx.state,
    )

    _render.finish(ctx)
