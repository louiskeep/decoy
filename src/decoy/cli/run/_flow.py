"""The skeleton of a `decoy run`: the order of the phases, the error arm and the cleanup."""

import contextlib
import time
from datetime import datetime, timezone

import typer

from decoy.cli.io import mint_invocation_id
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


def execute(ctx: RunContext) -> None:
    """Run the phases in order. Everything after the `try` runs only on success."""
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
        # The exit code is decided by now (`fail` raised its typer.Exit above).
        _end_trace(_otel, _trace, ok=finished, error_class=_failed_with)
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
