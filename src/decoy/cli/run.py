"""`decoy run` -- execute a masking or synthetic-generation pipeline.

CLI.1 commit 3 (2026-06-01): rewired against the V2 engine spine.
Non-chunked runs (the default) go through `run_pipeline`, the engine's
unified entry point that profiles, compiles, and executes mask + generate
tables in one call, using the engine's internal `PandasExecutionAdapter`.
`--chunked` is a separate streaming path (`run_mask_pipeline_chunked`),
mask-only, which still supports substrate selection via
`select_execution_adapter`. `graph` and `convert` are V1-only and have
no engine; the choke-point validator rejects them with a typed error
before this module sees them.
"""

import binascii
import json as _json
import time
from enum import Enum
from pathlib import Path

import typer

from decoy import __version__ as _cli_version
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import spinner
from decoy.ui.theme import error, hint, warn


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"


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

  decoy run pipeline.yaml --chunked --substrate polars
    Stream with polars instead of the chunked-path pandas default.
    (--substrate only affects --chunked runs; plain runs always use pandas.
    See: decoy explain substrate.)

See also: decoy validate, decoy explain chunked, decoy explain vault.
"""


class _VaultUsageError(Exception):
    """--vault on a config that cannot vault; user error (exits EXIT_USAGE)."""


class _ChunkedGenerateError(Exception):
    """--chunked with a generate-table config; user error (exits EXIT_USAGE)."""


def _load_raw_config(config_path: Path) -> dict | None:
    """Single defensive YAML parse for the pre-flight helpers.

    Audit L3 (2026-06-12): the config was read + parsed up to 4x per
    run (_detect_mode, _detect_key_label, the spinner body, the
    follow-up hint) -- a perf cliff on large or network-mounted
    configs. Helpers now share one parse; the spinner body still
    re-raises real parse errors through its own load so the error
    path is unchanged.
    """
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None


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
            "64-char hex master key for keyed deterministic masking. "
            "Same key + same --key-label always yield bitwise-identical "
            "output across runs and machines. Reads DECOY_MASTER_KEY env "
            "var when omitted; without either, masking falls back to the "
            "legacy seeded path (per-input deterministic but not portable)."
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
            "Sources/targets may be CSV or Parquet. See: decoy explain chunked."
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
    substrate: str = typer.Option(
        None,
        "--substrate",
        envvar="DECOY_SUBSTRATE",
        help=(
            "Execution substrate for --chunked runs: pandas (default) or polars. "
            "Non-chunked (plain) runs always use the engine's pandas adapter "
            "(the V2 unified run_pipeline path); this flag and the DECOY_SUBSTRATE "
            "env var are only consulted for --chunked runs. Setting either on a "
            "plain run emits a warning to stderr and is otherwise ignored. "
            "Cross-substrate outputs are value-equal; CSV bytes may differ only "
            "via Arrow type-width drift, which CSV does not carry."
        ),
    ),
    key_label: str = typer.Option(
        None,
        "--key-label",
        help=(
            "Stable namespace string for the masking key hierarchy. "
            "Required when --master-key is set. Pick something durable "
            "(e.g. 'customers_q4'); changing it produces a different "
            "masked output. Read from the YAML's top-level 'key_label:' "
            "field if not passed on the command line."
        ),
    ),
    evidence_out: Path = typer.Option(
        None,
        "--evidence-out",
        help=(
            "Write a local evidence manifest (JSON) to this path after a "
            "successful run. The manifest records pipeline hash, input/output "
            "file fingerprints, row counts, and run metadata. It does NOT "
            "contain raw data values. Use `decoy evidence verify` to check "
            "the manifest against current files. "
            "See: decoy explain evidence (when available)."
        ),
    ),
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking or synthetic-generation job described in
    YAML. The engine handles its own logging per the YAML's `logging:`
    section; flags here only affect CLI-side output.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    raw_cfg = _load_raw_config(config)
    yaml_mode = _detect_mode(raw_cfg) or mode.value

    resolver = _build_resolver(master_key, key_label, raw_cfg, state)

    # Warn when --substrate (or DECOY_SUBSTRATE) is set on a non-chunked run.
    # The flag is only consulted on the --chunked path; plain runs hardcode
    # the engine's PandasExecutionAdapter. Warning to stderr only; do not
    # suppress in --json mode (json goes to stdout); suppress in --quiet.
    if substrate is not None and not chunked and state.mode is not OutputMode.quiet:
        state.err_console.print(
            warn("warning:"),
            "--substrate is only consulted for --chunked runs; "
            "this plain run uses the engine's pandas adapter.",
        )

    # Sentinels for evidence manifest building (set on successful plain run).
    _ev_config_dict: dict | None = None
    _ev_engine_version: str | None = None
    _ev_row_counts: dict | None = None

    started = time.perf_counter()
    try:
        with spinner(state, f"Running {yaml_mode}..."):
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

                raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw).model_dump()
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

            vault_writer = None
            if vault is not None:
                from decoy_engine import vault_writer_for_config
                from decoy_engine.vault import iter_vault_columns

                if not iter_vault_columns(config_dict):
                    raise _VaultUsageError(
                        "--vault was passed but no column declares vault: true "
                        "in this config. Add `vault: true` to the columns whose "
                        "source values the vault should record."
                    )
                vault_writer = vault_writer_for_config(config_dict)

            if chunked:
                _run_chunked_mask(
                    config_dict, config.parent, chunk_size, substrate, vault_writer
                )
            else:
                sources = _load_sources_from_config(config_dict, config.parent)
                instance_locale = (config_dict.get("global_settings") or {}).get(
                    "default_locale"
                )
                result = run_pipeline(
                    config_dict,
                    sources,
                    engine_version=engine_version,
                    derive_key=resolver,
                    instance_default_locale=instance_locale,
                    vault_writer=vault_writer,
                )
                _write_mask_outputs(config_dict, result, config.parent)
                if evidence_out is not None:
                    _ev_row_counts = {
                        name: len(tbl) for name, tbl in result.outputs.items()
                    }
            if vault_writer is not None:
                vault_writer.write(vault)
    except typer.Exit:
        # CLI QA fix (2026-06-02, F7): an inner call site that raises
        # typer.Exit (e.g. a library that vendored Typer) has already
        # set its intended exit code. Do not swallow it into the
        # EXIT_RUNTIME catch-all below.
        raise
    except Exception as exc:
        # Audit H10 (2026-06-12): dispatch on exception type so scripts
        # can tell "your config is wrong" (EXIT_USAGE, per the
        # exit_codes.py contract) from "the run blew up" (EXIT_RUNTIME).
        # Imported lazily to keep the engine import off the help path.
        from decoy_engine import ConfigError, PipelineValidationError
        from decoy_engine.plan import PlanCompileError

        _exit_code = (
            EXIT_USAGE
            if isinstance(
                exc,
                (
                    PlanCompileError,
                    PipelineValidationError,
                    ConfigError,
                    _ChunkedGenerateError,
                    _VaultUsageError,
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
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "run",
                    "status": "error",
                    "config": config_str,
                    "mode": yaml_mode,
                    "error": error_text,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), error_text)
            state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback."
            )
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=_exit_code)

    elapsed = time.perf_counter() - started

    # Write evidence manifest if --evidence-out was given and we have the data.
    # Only available for non-chunked plain runs (chunked path does not return
    # an ExecutionResult, so row counts are not available).
    if evidence_out is not None and _ev_config_dict is not None:
        from decoy.cli.evidence import build_manifest

        _label = key_label or _detect_key_label(raw_cfg)
        manifest = build_manifest(
            pipeline_path=config,
            config_dict=_ev_config_dict,
            run_result={"row_counts": _ev_row_counts or {}},
            cli_version=_cli_version,
            engine_version=_ev_engine_version or "unknown",
            key_label=_label,
        )
        evidence_out.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
        if state.mode is not OutputMode.json and state.mode is not OutputMode.quiet:
            from decoy.ui.theme import success as _success

            state.console.print(
                _success("Evidence:"), str(evidence_out)
            )

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "run",
                "status": "ok",
                "config": config_str,
                "mode": yaml_mode,
                "elapsed_s": round(elapsed, 3),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    render_card(
        state,
        command="decoy run",
        facts=[
            ("Pipeline", config.name),
            ("Mode", yaml_mode),
            ("Elapsed", f"{elapsed:.2f}s"),
        ],
        next_hint=_next_hint_for_run(raw_cfg, mode),
        status="ok",
    )


def _build_resolver(
    master_key_hex: str | None, key_label: str | None, raw_cfg: dict | None, state
):
    """Construct the engine-facing ``derive_key`` resolver, or None when no
    master key was supplied. Keeps the legacy seeded fallback default so
    runs without a key behave exactly as before."""
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
        raise typer.BadParameter(
            f"--master-key must decode to 32 bytes (got {len(master)})."
        )

    label = key_label or _detect_key_label(raw_cfg)
    if not label:
        raise typer.BadParameter(
            "--master-key requires a --key-label (or top-level 'key_label:' "
            "in the YAML). Pick a stable namespace string like 'customers_q4'."
        )

    from decoy_engine import make_key_resolver

    return make_key_resolver(master, label)


def _detect_key_label(raw_cfg: dict | None) -> str | None:
    """Read the top-level ``key_label:`` from the parsed YAML, or None."""
    if isinstance(raw_cfg, dict):
        label = raw_cfg.get("key_label")
        if isinstance(label, str) and label.strip():
            return label.strip()
    return None


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
        out = (
            raw_cfg.get("output", {}).get("path") if isinstance(raw_cfg, dict) else None
        )
        if out:
            return f"head {out}"
    except Exception:
        pass
    return None


def _run_chunked_mask(
    config_dict: dict,
    base_dir: Path,
    chunk_size: int,
    substrate: str | None = None,
    vault_writer=None,
) -> None:
    """WS4 chunked mask path: stream each mask table's source through
    `decoy_engine.run_mask_pipeline_chunked`, writing output per chunk.

    The engine's `check_chunked_compatibility` rejects anything that is
    not value-keyed (PlanCompileError -> EXIT_USAGE via the H10 typed
    dispatch), so a chunked run that starts is guaranteed byte-identical
    to a plain run of the same config for CSV targets. Parquet targets
    are VALUE-equal to a plain run; their file bytes are stable for a
    fixed (chunk_size, pyarrow version) but not across chunk sizes,
    because each chunk writes one row group.

    Formats: CSV and parquet, on either side independently (suffix
    picks the reader/writer, mirroring the plain path's free mixing).
    Parquet reads stream via ParquetFile.iter_batches; CSV reads keep
    the dtype=str contract of the plain path, so a csv -> parquet run
    produces an all-string schema.

    `substrate` None keeps the chunked default (pandas, the byte-stable
    contract this mode shipped with); an explicit value selects the
    adapter via the engine's `select_execution_adapter`."""
    from decoy_engine import __version__ as engine_version
    from decoy_engine import run_mask_pipeline_chunked
    from decoy_engine.execution import select_execution_adapter

    adapter = (
        select_execution_adapter(substrate=substrate) if substrate is not None else None
    )

    sources = config_dict.get("sources") or {}
    targets = config_dict.get("targets") or {}
    for table_entry in config_dict.get("tables") or []:
        if not isinstance(table_entry, dict) or not table_entry.get("columns"):
            continue
        name = table_entry.get("name")
        src_spec = sources.get(name) if isinstance(sources, dict) else None
        tgt_spec = targets.get(name) if isinstance(targets, dict) else None
        if not isinstance(src_spec, dict) or not isinstance(src_spec.get("path"), str):
            continue
        src_path = _resolve_path(src_spec["path"], base_dir)
        if not isinstance(tgt_spec, dict) or not isinstance(tgt_spec.get("path"), str):
            continue
        out_path = _resolve_path(tgt_spec["path"], base_dir)

        masked_iter = run_mask_pipeline_chunked(
            config_dict,
            _iter_source_chunks(src_path, chunk_size),
            table=name,
            engine_version=engine_version,
            adapter=adapter,
            vault_writer=vault_writer,
        )
        _write_chunked_output(masked_iter, out_path, src_path)


def _iter_source_chunks(src_path: Path, chunk_size: int):
    """Yield pa.Tables of at most `chunk_size` rows from a CSV or parquet file.

    Parquet batches can come back SHORTER than chunk_size at row-group
    boundaries; that is fine and must stay fine -- chunked output is
    chunking-invariant by the engine's parity contract, so nobody should
    "fix" the short batches by re-buffering.
    """
    import pandas as pd
    import pyarrow as pa

    if src_path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(str(src_path))
        for batch in parquet_file.iter_batches(batch_size=chunk_size):
            yield pa.Table.from_batches([batch])
        return
    for df in pd.read_csv(src_path, dtype=str, chunksize=chunk_size):
        yield pa.Table.from_pandas(df, preserve_index=False)


def _write_chunked_output(masked_iter, out_path: Path, src_path: Path) -> None:
    """Stream masked chunks to `out_path`, format picked by its suffix."""
    if out_path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        writer = None
        try:
            for masked in masked_iter:
                if writer is None:
                    writer = pq.ParquetWriter(str(out_path), masked.schema)
                writer.write_table(masked)
            if writer is None and src_path.suffix.lower() == ".parquet":
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
        masked.to_pandas().to_csv(
            out_path, index=False, header=first, mode="w" if first else "a"
        )
        first = False


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    """Resolve a YAML path against the config's directory.

    Mirrors `decoy plan`'s source-loading behavior: relative paths in the
    YAML resolve relative to the YAML file's directory, not the CWD.
    Absolute paths pass through unchanged.
    """
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _load_sources_from_config(config_dict: dict, base_dir: Path) -> dict:
    """Read each `sources[table]` into a `dict[str, pa.Table]`.

    Accepts CSV and Parquet by file extension. Sources without a `path`
    field are skipped (the engine treats absent tables as empty, but
    the mask spine will error on a missing source if the plan needs it;
    leave that error to the engine layer).
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    out: dict[str, pa.Table] = {}
    sources = config_dict.get("sources") or {}
    if not isinstance(sources, dict):
        return out
    for table_name, src in sources.items():
        if not isinstance(src, dict):
            continue
        raw_path = src.get("path")
        if not isinstance(raw_path, str):
            continue
        path = _resolve_path(raw_path, base_dir)
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            out[table_name] = pq.read_table(str(path))
        else:
            df = pd.read_csv(path, dtype=str)
            out[table_name] = pa.Table.from_pandas(df, preserve_index=False)
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
    """
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
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            import pyarrow.parquet as pq

            pq.write_table(table, str(path))
        else:
            table.to_pandas().to_csv(path, index=False)


# The epilog is wired by __main__ at command registration time; the
# docstring on `run` stays as the help body.
RUN_EPILOG = _RUN_EPILOG
