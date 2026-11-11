"""The skeleton of a `decoy run`: the order of the phases, the error arm and the cleanup."""

import contextlib
import time
from datetime import datetime, timezone

import typer

from decoy.cli.run import _errors, _evidence, _execute, _prepare, _render
from decoy.cli.run._context import RunContext
from decoy.cli.run._notify import _dispatch_run_notifications, _start_telemetry, parse_channels
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
    try:
        # F30: refuse a bad telemetry setting before any work. Spans and the exit
        # flush bind to `_otel` in C1b.
        _otel = _start_telemetry(ctx.otel_endpoint, ctx.state)
        with spinner(ctx.state, f"Running {ctx.yaml_mode}..."), contextlib.ExitStack() as _scopes:
            if ctx.rows is None:
                _prepare.prepare(ctx, _scopes)
                _execute.execute(ctx)
            else:
                _prepare.prepare_preview(ctx)
                _execute.execute_preview(ctx)
    except typer.Exit:
        # An inner typer.Exit already set its exit code; keep it out of the catch-all below.
        raise
    except Exception as exc:
        _errors.fail(ctx, exc)
    finally:
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
