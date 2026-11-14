"""The skeleton of a `decoy run`: the order of the phases, the error arm and the cleanup."""

import contextlib
import time
from datetime import datetime, timezone

import typer

from decoy._private_file import PrivateFileError
from decoy.cli.io import RunLayout, mint_invocation_id
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


def _child_flags(ctx: RunContext) -> list[str]:
    """The options each `--all` child gets. The master key goes by environment, never argv."""
    flags = ["--mode", ctx.mode.value, "--notify-on", ctx.notify_on.value]
    valued = (
        ("--mask-secret", ctx.mask_secret),
        ("--chunk-size", ctx.chunk_size),
        ("--max-memory", ctx.max_memory),
        ("--threads", ctx.threads),
        ("--key-label", ctx.key_label),
        ("--otel-endpoint", ctx.otel_endpoint),
        ("--rows", ctx.rows),
    )
    for flag, value in valued:
        if value is not None:
            flags += [flag, str(value)]
    for flag, values in (("--notify", ctx.notify), ("--duckdb-source", ctx.duckdb_source)):
        for value in values:
            flags += [flag, value]
    switches = (
        ("-v", ctx.verbose),
        ("--chunked", ctx.chunked),
        ("--native", ctx.native),
        ("--no-native", ctx.no_native),
        ("--explain-plan", ctx.explain_plan),
        ("--fidelity", ctx.fidelity),
        ("--post-validate", ctx.post_validate),
        ("--post-validate-enforce", ctx.post_validate_enforce),
    )
    return flags + [flag for flag, on in switches if on]


def _bind_pipeline(ctx: RunContext) -> None:
    """Fan out for `--all`, else settle which YAML this process runs (given, or the only one)."""
    if ctx.all_:
        refused = [
            flag
            for flag, value in (
                ("--evidence-out", ctx.evidence_out),
                ("--vault", ctx.vault),
                ("--out-dir", ctx.out_dir),
            )
            if value is not None
        ]
        key = {"DECOY_MASTER_KEY": ctx.master_key} if ctx.master_key is not None else {}
        run_all(
            ctx.state,
            ctx.cli,
            named=ctx.pipeline is not None,
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
                    ctx.layout = RunLayout.out_dir(ctx.out_dir)
                except (OSError, PrivateFileError, ValueError):
                    failed = True
                if failed:
                    raise _errors.OutDirUsageError("Could not create or use --out-dir.")
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
