"""How `decoy run` executes: the chunked and plain branches, and the source and target I/O."""

from functools import partial
from pathlib import Path

from decoy import _native_gate, _resources
from decoy.cli import gen
from decoy.cli.extras import check_cloud_endpoints, check_cloud_endpoints_supported
from decoy.cli.io import (
    RunLayout,
    check_target_formats,
    iter_source_chunks,
    open_run_layout,
    parquet_schema,
    read_source,
    resolve_target_format,
    resolved_source_config,
    table_records,
    write_chunked_output,
    write_targets,
)
from decoy.cli.io import (
    resolve_path as _resolve_path,
)
from decoy.cli.run._context import DEFAULT_CHUNK_SIZE, RunContext
from decoy.cli.run._vault import _commit_vault


class _ChunkedGenerateError(Exception):
    """--chunked with a generate-table config; user error (exits EXIT_USAGE)."""


class _ChunkedFixedWidthError(Exception):
    """--chunked with a fixed_width source; user error (exits EXIT_USAGE)."""


class _ChunkedQuarantineError(Exception):
    """--chunked with quarantine enabled; user error (exits EXIT_USAGE).

    The chunked path streams through `run_mask_pipeline_chunked`, which takes no quarantine
    path, so the rows quarantine would hold are never written there. Refused before any
    source is read rather than run without the quarantine the config asks for.
    """


class _ChunkedReportFlagError(Exception):
    """--chunked combined with a report flag (--explain-plan / --fidelity /
    --post-validate[-enforce]); user error (exits EXIT_USAGE).

    S5 (2026-10-23): the four report flags surface fields of the non-chunked
    `run_pipeline`'s `ExecutionResult.quality_metrics`. The `--chunked` path
    (`_run_chunked_mask`) streams mask-only and returns no `ExecutionResult`,
    so there is nothing to read those fields off. Reject the combination
    loudly rather than silently dropping the requested report (plan P2-3)."""


def _run_chunked_mask(
    config_dict: dict,
    base_dir: Path,
    chunk_size: int,
    layout: RunLayout,
    key_provider=None,
    ledger: dict[str, Path] | None = None,
) -> dict[str, Path | None]:
    """WS4 chunked mask path: stream each mask table's source through
    `decoy_engine.run_mask_pipeline_chunked`, writing output per chunk, on
    the engine's one execution adapter (pandas; the chunked path has no
    `ExecutionResult`, so the caller labels the route itself).

    The engine's `check_chunked_compatibility` rejects anything that is
    not value-keyed (PlanCompileError -> EXIT_USAGE via the H10 typed
    dispatch), so a chunked run that starts is guaranteed byte-identical
    to a plain run of the same config for CSV targets. Parquet targets
    are VALUE-equal to a plain run; their file bytes are stable for a
    fixed (chunk_size, pyarrow version) but not across chunk sizes,
    because each chunk writes one row group.

    Formats: CSV and parquet, on either side independently. The source
    reader and the writer follow the declared `format` of the source and the
    target. Parquet reads stream via ParquetFile.iter_batches; CSV reads keep
    the dtype=str contract of the plain path, so a csv -> parquet run
    produces an all-string schema.

    Returns table name to the path actually published, or None for a table whose empty CSV
    source published nothing. `ledger` gets each published path right after its writer
    returns, so a later table's failure keeps the earlier entries."""
    _require_local_io_endpoints(config_dict)
    check_target_formats(config_dict, chunked=True)

    from decoy_engine import __version__ as engine_version
    from decoy_engine import run_mask_pipeline_chunked

    sources = config_dict.get("sources") or {}
    targets = config_dict.get("targets") or {}
    published: dict[str, Path | None] = {}
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

        masked_iter = run_mask_pipeline_chunked(
            config_dict,
            iter_source_chunks(name, src_spec, base_dir, chunk_size),
            table=name,
            engine_version=engine_version,
            key_provider=key_provider,
        )
        written = published[name] = write_chunked_output(
            masked_iter,
            resolve_target_format(name, tgt_spec),
            tgt_spec["path"],
            layout,
            empty_schema=(
                partial(parquet_schema, src_path) if src_spec.get("format") == "parquet" else None
            ),
        )
        if ledger is not None and written is not None:
            ledger[name] = written
    return published


def _check_chunked_tables(config_dict: dict) -> None:
    """The config-only chunked checks: quarantine, target formats, then the engine's per
    mask table."""
    quarantine = config_dict.get("quarantine")
    if isinstance(quarantine, dict) and quarantine.get("enabled"):
        raise _ChunkedQuarantineError(
            "--chunked does not support quarantine (quarantine.enabled is true). "
            "Run without --chunked, or turn quarantine off."
        )
    check_target_formats(config_dict, chunked=True)
    from decoy_engine import get_default_registry
    from decoy_engine.execution import check_chunked_compatibility

    registry = get_default_registry()
    for entry in config_dict.get("tables") or []:
        if isinstance(entry, dict) and entry.get("columns"):
            check_chunked_compatibility(config_dict, table=entry["name"], registry=registry)


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
    work is done and `_write_mask_outputs` finds nowhere to put it. A target whose declared
    format contradicts its suffix is refused here too, before the first read.
    """
    _require_local_io_endpoints(config_dict)
    check_target_formats(config_dict, chunked=False)

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


def _write_mask_outputs(
    config_dict: dict, result, layout: RunLayout, published: dict[str, Path] | None = None
) -> dict[str, Path]:
    """Write each declared target from the V2 ExecutionResult.

    The engine result exposes masked tables on `outputs` (dict[table_name -> pa.Table]);
    the `targets:` block is a dict keyed by table name. Each file is written by its
    declared `format` through `cli/io/_targets.py`, and a format that contradicts the path
    suffix is refused before the first table is written.

    Refuses s3/gcs targets rather than skipping them, for a caller that
    writes without having gone through `_load_sources_from_config`.
    """
    _require_local_io_endpoints(config_dict)
    check_target_formats(config_dict, chunked=False)

    outputs = getattr(result, "outputs", None)
    if not isinstance(outputs, dict):
        return {}
    return write_targets(config_dict, outputs, layout, published)


def execute(ctx: RunContext) -> None:
    """Run the pipeline on the chunked or plain branch and record what the tail reports."""
    # After the gate and before the first write, open the run folder, claim and `out/`.
    # A fixed `--out-dir` was already opened before prepare could read a source.
    if ctx.layout is None:
        ctx.layout = open_run_layout(ctx.config, ctx.config_dict, ctx.invocation_id)
    layout = ctx.layout
    if ctx.chunked:
        _chunk_paths = _run_chunked_mask(
            ctx.config_dict,
            ctx.config.parent,
            ctx.chunk_size or DEFAULT_CHUNK_SIZE,
            layout,
            ctx.key_provider,
            ctx._published,
        )
        ctx._table_records = table_records(dict.fromkeys(_chunk_paths), _chunk_paths)
        ctx._native_route = _native_gate.classify_route(
            chunked=True,
            any_generate=ctx.any_generate,
            quality_metrics=None,
        )
    else:
        from decoy_engine import run_pipeline

        _key_kwargs = {} if ctx.key_provider is None else {"key_provider": ctx.key_provider}
        instance_locale = (ctx.config_dict.get("global_settings") or {}).get("default_locale")
        # S5 report kwargs are passed only when a report flag was requested, so
        # the default call shape stays valid on an older engine (the native-compat
        # contract in test_run_native).
        _report_kwargs = (
            {
                "explain_plan": ctx.explain_plan,
                "fidelity_report": ctx.fidelity,
                "post_validation": ctx.post_validation,
                "post_validation_enforce": ctx.post_validate_enforce,
            }
            if ctx._report_flags
            else {}
        )
        # Sent only when set, so an engine without the keyword still runs a config without it.
        quarantine_path = layout.place_quarantine(ctx.config_dict)
        quarantine_kwargs = {"quarantine_path": quarantine_path} if quarantine_path else {}
        result = run_pipeline(
            resolved_source_config(ctx.config_dict, ctx.config.parent),
            ctx.sources,
            engine_version=ctx.engine_version,
            derive_key=ctx.resolver,
            instance_default_locale=instance_locale,
            vault_writer=ctx.vault_writer,
            base_dir=ctx.config.parent,
            **quarantine_kwargs,
            **_key_kwargs,
            **_report_kwargs,
            **_native_gate.run_pipeline_kwargs(ctx.gate_result),
            **_resources.run_pipeline_kwargs(ctx._res),
        )
        ctx._native_route = _native_gate.classify_route(
            chunked=False,
            any_generate=ctx.any_generate,
            quality_metrics=result.quality_metrics,
        )
        # Stage 2 (approach 2): assert --native's compiled-kernel
        # evidence BEFORE the first write on this path. A no-op for
        # default/--no-native intent.
        _native_gate.post_run_verify(intent=ctx.native_intent, route=ctx._native_route)
        # The vault is durable BEFORE any output is published: masked output whose
        # vault was lost can never be reversed.
        if ctx.vault_writer is not None:
            _commit_vault(ctx.vault_writer, ctx.vault)
        _written = _write_mask_outputs(ctx.config_dict, result, layout, ctx._published)
        ctx._table_records = table_records(
            {name: len(tbl) for name, tbl in result.outputs.items()}, _written
        )
        # S5: capture the quality metrics so the tail can render the
        # requested report sections and apply the enforce -> EXIT_FINDINGS
        # mapping. The mask has already succeeded and its outputs are
        # written above; enforce only changes the EXIT CODE, never whether
        # output is produced (plan P1-2 -- the engine never fails the job).
        if ctx._report_flags:
            ctx._report_quality_metrics = dict(result.quality_metrics)
        if ctx.evidence_out is not None:
            ctx._ev_row_counts = {name: len(tbl) for name, tbl in result.outputs.items()}
        ctx._ev_timings = result.timings
        ctx._ev_engine_warnings = result.warnings
        ctx._notify_row_count = sum(len(tbl) for tbl in result.outputs.values())


def execute_preview(ctx: RunContext) -> None:
    """Run the scaled generate pipeline and keep its sampled rows. Nothing is written."""
    from decoy_engine import run_pipeline
    from decoy_engine.generation import generation_order

    assert ctx.rows is not None
    instance_locale = (ctx.config_dict.get("global_settings") or {}).get("default_locale")
    result = run_pipeline(
        resolved_source_config(ctx.config_dict, ctx.config.parent),
        {},
        engine_version=ctx.engine_version,
        derive_key=ctx.resolver,
        instance_default_locale=instance_locale,
        base_dir=ctx.config.parent,
        **_resources.run_pipeline_kwargs(ctx._res),
    )
    order = [name for name, _parents in generation_order(ctx.config_dict)]
    ctx._preview_tables = gen.sample_tables(result.outputs, order, ctx.rows)
    ctx._ev_engine_warnings = result.warnings
