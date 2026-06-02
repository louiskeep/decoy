"""`decoy run` -- execute a masking or synthetic-generation pipeline.

CLI.1 commit 3 (2026-06-01): rewired against the V2 engine spine
(`PipelineConfig` -> `compile_plan` -> `select_execution_adapter` ->
`generate_tables`). The V1 graph runner + `Masker` + `DataGenerator`
imports were deleted in storm-reframe-C / S22; this module imported
them. The V2 spine accepts two modes (`mask`, `generate`); `graph`
and `convert` are V1-only and have no engine. The choke-point
validator rejects them with a typed error before this module sees
them.
"""

import binascii
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import spinner
from decoy.ui.theme import error, hint


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"


_RUN_EPILOG = """\
Examples:

  decoy run pipeline.yaml
    Run with default mode (mask).

  decoy run pipeline.yaml --json
    Suppress chrome and emit a structured result for scripting.

See also: decoy validate.
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
            "64-char hex master key for keyed deterministic masking. "
            "Same key + same --key-label always yield bitwise-identical "
            "output across runs and machines. Reads DECOY_MASTER_KEY env "
            "var when omitted; without either, masking falls back to the "
            "legacy seeded path (per-input deterministic but not portable)."
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
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking or synthetic-generation job described in
    YAML. The engine handles its own logging per the YAML's `logging:`
    section; flags here only affect CLI-side output.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    yaml_mode = _detect_mode(config) or mode.value

    resolver = _build_resolver(master_key, key_label, config, state)

    started = time.perf_counter()
    try:
        with spinner(state, f"Running {yaml_mode}..."):
            from decoy_engine import (
                PipelineConfig,
                compile_plan,
                generate_tables,
                get_default_registry,
                select_execution_adapter,
                __version__ as engine_version,
            )
            from decoy_engine.profile import profile_source
            from decoy_engine.relationships import (
                RelationshipGraph,
                build_namespace_registry,
                build_relationship_graph,
                check_orphan_fk_policy_completeness,
            )

            yaml_text = config.read_text(encoding="utf-8")
            import yaml as _yaml

            raw = _yaml.safe_load(yaml_text)
            config_dict = PipelineConfig.model_validate(raw).model_dump()

            if config_dict.get("mode") == "generate":
                instance_locale = (config_dict.get("global_settings") or {}).get(
                    "default_locale"
                )
                tables = generate_tables(
                    config_dict,
                    derive_key=resolver,
                    instance_default_locale=instance_locale,
                )
                _write_generate_outputs(config_dict, tables, config.parent)
            else:
                # mask is the default.
                job_seed = (config_dict.get("global_settings") or {}).get("seed")
                profile = profile_source(
                    config_dict,
                    seed=job_seed if isinstance(job_seed, int) else None,
                )
                plan = compile_plan(
                    config_dict, profile, decoy_engine_version=engine_version
                )
                ns_registry = build_namespace_registry(config_dict, profile)
                if profile.relationships:
                    lookup = check_orphan_fk_policy_completeness(
                        config_dict, profile.relationships
                    )
                    graph = build_relationship_graph(
                        profile.relationships,
                        namespace_registry=ns_registry,
                        orphan_policy_lookup=lookup,
                    )
                else:
                    graph = RelationshipGraph(edges=(), ordering=())

                sources = _load_sources_from_config(config_dict, config.parent)
                adapter = select_execution_adapter()
                result = adapter.run(
                    plan,
                    sources,
                    registry=get_default_registry(),
                    relationship_graph=graph,
                    namespace_registry=ns_registry,
                )
                _write_mask_outputs(config_dict, result, config.parent)
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "run",
                    "status": "error",
                    "config": config_str,
                    "mode": yaml_mode,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    elapsed = time.perf_counter() - started

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
        next_hint=_next_hint_for_run(config, mode),
        status="ok",
    )


def _build_resolver(master_key_hex: str | None, key_label: str | None, config_path: Path, state):
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

    label = key_label or _detect_key_label(config_path)
    if not label:
        raise typer.BadParameter(
            "--master-key requires a --key-label (or top-level 'key_label:' "
            "in the YAML). Pick a stable namespace string like 'customers_q4'."
        )

    from decoy_engine import make_key_resolver
    return make_key_resolver(master, label)


def _detect_key_label(config_path: Path) -> str | None:
    """Read the top-level ``key_label:`` from the YAML, or return None."""
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            label = cfg.get("key_label")
            if isinstance(label, str) and label.strip():
                return label.strip()
    except Exception:
        pass
    return None


def _detect_mode(config_path: Path) -> str | None:
    """Read the top-level ``mode:`` from the YAML, or return None if absent.

    The choke-point validator (`PipelineConfig.model_validate`) rejects
    any mode other than `mask` or `generate`; this helper exists so the
    spinner can pre-label the run before validation fires. Returns the
    raw string; trust the choke-point to reject `graph` / `convert`.
    """
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            m = cfg.get("mode")
            if isinstance(m, str):
                return m.lower()
    except Exception:
        pass
    return None


def _next_hint_for_run(config: Path, mode: "Mode") -> str | None:
    """Best-effort follow-up hint based on the YAML's output path."""
    try:
        import yaml

        cfg = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        out = cfg.get("output", {}).get("path") if isinstance(cfg, dict) else None
        if out:
            return f"head {out}"
    except Exception:
        pass
    return None


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


def _write_generate_outputs(config_dict: dict, tables: dict, base_dir: Path) -> None:
    """Write each declared target from a generate-mode run.

    `generate_tables` returns `dict[str, pa.Table]`. The V2 `targets:`
    block is a dict keyed by table name (same shape as mask). CLI.3
    commit 2 (2026-06-02) fix: pre-fix iterated `targets` as a list.
    """
    targets = config_dict.get("targets") or {}
    if not isinstance(targets, dict):
        return
    for table_name, entry in targets.items():
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        table = tables.get(table_name)
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


run.__doc__ = run.__doc__  # keep docstring; epilog wired by __main__ on registration


RUN_EPILOG = _RUN_EPILOG
