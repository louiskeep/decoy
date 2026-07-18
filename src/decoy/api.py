"""decoy.mask() / decoy.scan() -- the library one-liner API (OSS-launch S6).

Thin wrappers over `decoy_engine`'s existing public entrypoints. They reuse
the exact CLI helper functions `decoy run` / `decoy storm analyze` call
(config loading, source loading, mask-secret validation, output writing) so
`import decoy; decoy.mask(...)` walks the SAME engine path as the CLI --
same determinism, same keyed-secret fail-closed gate -- never a
reimplementation of masking or scanning. See CLAUDE.md: "the CLI is a thin
wrapper around decoy-engine; all data logic lives in the engine."

    decoy.mask(...)  wraps decoy_engine.run_pipeline  (the call `decoy run`
                      makes for non-chunked runs).
    decoy.scan(...)  wraps decoy_engine.run_storm     (the call
                      `decoy storm analyze` makes).

Both accept a config/source shaped exactly like the pipeline YAML `decoy
run` consumes (a dict with `version`, `global_settings`, `tables`,
`targets`, ...) -- this library does not invent a simplified config
schema. The one-liner convenience is in accepting that config as a dict (no
YAML file required) and a DataFrame directly (no CSV round-trip required),
plus returning the masked DataFrame(s) in memory.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from decoy.cli.run import (
    _is_valid_mask_secret_ref,
    _load_sources_from_config,
    _write_mask_outputs,
)
from decoy.cli.storm import InputFormat, SampleStrategy, _load_data, _parse_layout
from decoy.cli.storm import _infer_format as _storm_infer_format

__all__ = [
    "ConfigValidationError",
    "MaskSecretConfigError",
    "mask",
    "scan",
]


class MaskSecretConfigError(ValueError):
    """A mask_secret / mask_secret_ref value was missing, malformed, or
    conflicting. Public-library equivalent of the CLI's
    `decoy.cli.run._MaskSecretUsageError` (`--mask-secret`) usage-error
    contract -- same checks, same fail-closed guarantees, library-shaped
    exception type."""


class ConfigValidationError(ValueError):
    """The pipeline config failed `PipelineConfig` schema validation."""


DataInput = "str | Path | pd.DataFrame | Mapping[str, pd.DataFrame | pa.Table] | None"
ConfigInput = "str | Path | dict"


def _load_config_dict(config: Any) -> dict:
    """Load the raw pipeline config into a dict, from a YAML path or a dict
    already shaped like the YAML. Mirrors `decoy.cli.run`'s YAML load, minus
    the CLI's defensive swallow-and-reparse trick (a library call should
    raise the real parse error immediately, not defer it).

    Deep-copies a dict `config` before returning: `mask()` mutates the
    working dict (mask-secret injection, `out` target merging) and must
    never mutate a dict the caller still owns."""
    if isinstance(config, dict):
        import copy

        return copy.deepcopy(config)
    if isinstance(config, (str, Path)):
        import yaml

        path = Path(config)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigValidationError(
                f"{path}: expected a YAML mapping at the top level, got {type(raw).__name__}."
            )
        return raw
    raise TypeError(f"config must be a path (str/Path) or a dict, got {type(config).__name__}.")


def _validate_mask_secret_ref_shape(raw: dict) -> None:
    """Port of run.py's DE-02 secret-disclosure ROOT guard: reject a
    malformed `global_settings.mask_secret_ref` BEFORE
    `PipelineConfig.model_validate`, whose `ValidationError` echoes the
    offending value verbatim (a real secret-leak risk for a non-string ref,
    not just a CLI-cosmetic concern)."""
    raw_gs = raw.get("global_settings") if isinstance(raw, dict) else None
    if raw_gs is not None and not isinstance(raw_gs, dict):
        raise MaskSecretConfigError(
            f"global_settings must be a mapping (key: value pairs), not a {type(raw_gs).__name__}."
        )
    raw_ref = raw_gs.get("mask_secret_ref") if isinstance(raw_gs, dict) else None
    if raw_ref is not None and not _is_valid_mask_secret_ref(raw_ref):
        raise MaskSecretConfigError(
            "Invalid global_settings.mask_secret_ref: expected an "
            "'env:NAME' or 'file:/PATH' reference to a >=32-byte secret. "
            "It is a REFERENCE, never the raw secret."
        )


def _apply_mask_secret(config_dict: dict, mask_secret: str | None) -> None:
    """Port of run.py's `--mask-secret` injection + effective-ref guard
    (DE-02 Option B): one secret source per run, chosen explicitly, and a
    fail-closed refusal when the installed engine predates DE-02's
    keyprovider (which would otherwise silently emit UNKEYED output)."""
    if mask_secret is not None:
        existing_ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
        if existing_ref is not None:
            raise MaskSecretConfigError(
                "mask_secret was passed but the config already sets "
                "global_settings.mask_secret_ref. Set the masking secret "
                "in exactly one place: drop mask_secret=, or remove "
                "mask_secret_ref from the config."
            )
        config_dict.setdefault("global_settings", {})["mask_secret_ref"] = mask_secret

    effective_ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
    if effective_ref is not None:
        if not _is_valid_mask_secret_ref(effective_ref):
            raise MaskSecretConfigError(
                "Invalid mask secret: expected an 'env:NAME' or 'file:/PATH' "
                "reference to a >=32-byte secret (from mask_secret= or "
                "global_settings.mask_secret_ref). It is a REFERENCE, never "
                "the raw secret."
            )
        try:
            import decoy_engine.keyprovider  # noqa: F401
        except ImportError as exc:
            raise MaskSecretConfigError(
                "a mask secret is configured (mask_secret_ref / "
                "mask_secret=) but the installed decoy-engine is too old "
                "to honor it -- it has no DE-02 keyprovider, so it would "
                "silently emit UNKEYED output. Upgrade to "
                "decoy-engine>=0.4.0."
            ) from exc


def _build_generation_resolver(master_key: str | bytes | None, key_label: str | None):
    """Port of run.py's `_build_resolver`, for the SYNTHETIC GENERATION key
    hierarchy (`generate_columns:`). Independent of `mask_secret` (masking's
    keyed determinism), exactly as the CLI keeps `--master-key` and
    `--mask-secret` independent."""
    if master_key is None:
        return None
    if key_label is None:
        raise ValueError("master_key requires key_label (a stable namespace string).")

    if isinstance(master_key, bytes):
        master = master_key
    else:
        raw = master_key.strip()
        if raw.lower().startswith("0x"):
            raw = raw[2:]
        try:
            master = bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError(f"master_key must be valid hex ({exc}).") from exc
    if len(master) != 32:
        raise ValueError(f"master_key must decode to 32 bytes (got {len(master)}).")

    from decoy_engine import make_key_resolver

    return make_key_resolver(master, key_label)


def _tables_matching(config_dict: dict, *, require_columns: bool) -> list[dict]:
    tables = config_dict.get("tables") or []
    if not isinstance(tables, list):
        return []
    if require_columns:
        return [t for t in tables if isinstance(t, dict) and t.get("columns")]
    return [t for t in tables if isinstance(t, dict)]


def _single_table_name(config_dict: dict, *, require_columns: bool, context: str) -> str:
    candidates = _tables_matching(config_dict, require_columns=require_columns)
    if len(candidates) != 1:
        names = [t.get("name") for t in candidates]
        raise ValueError(
            f"{context}: config declares {len(candidates)} matching table(s) "
            f"{names!r}; pass a dict keyed by table name instead."
        )
    return candidates[0]["name"]


def _to_pa_table(value: "pd.DataFrame | pa.Table") -> pa.Table:
    if isinstance(value, pa.Table):
        return value
    if isinstance(value, pd.DataFrame):
        return pa.Table.from_pandas(value, preserve_index=False)
    raise TypeError(
        f"data values must be a pandas DataFrame or pyarrow Table, got {type(value).__name__}."
    )


def _stage_source_entry(name: str, value: Any, tmp_paths: list[Path]) -> dict:
    """Return a `sources[name]` descriptor dict pointing at a REAL,
    readable file for `value`.

    `run_pipeline` unconditionally profiles from the config's declared
    `sources:` paths before execution (decoy_engine execution/_pipeline.py
    sequencing contract step 2, `profile_source(config, ...)`); the
    `sources` Mapping[str, pa.Table] argument only feeds the later
    materialization step, so a config whose declared path does not exist
    fails at the profiling stage regardless of what is passed there. A
    path `value` already IS such a file -- point at it directly. A
    DataFrame/Table `value` has no file yet, so it is spooled to a
    Parquet temp file (a lossless round-trip, unlike CSV's blanket
    stringification) purely so profiling has real bytes to read; the
    temp path is tracked in `tmp_paths` for post-run cleanup."""
    if isinstance(value, (str, Path)):
        path = Path(value)
        fmt = "parquet" if path.suffix.lower() in (".parquet", ".pq") else "csv"
        return {"type": "file", "format": fmt, "path": str(path)}

    table = _to_pa_table(value)
    import os
    import tempfile

    fd, tmp_name = tempfile.mkstemp(prefix=f"decoy-mask-{name}-", suffix=".parquet")
    os.close(fd)
    tmp_path = Path(tmp_name)
    import pyarrow.parquet as pq

    pq.write_table(table, str(tmp_path))
    tmp_paths.append(tmp_path)
    return {"type": "file", "format": "parquet", "path": str(tmp_path)}


def _stage_data_sources(raw: dict, data: Any, tmp_paths: list[Path]) -> None:
    """Mutate `raw['sources']` so every table `data` covers points at a
    real on-disk file (spooling DataFrames/Tables to temp Parquet via
    `_stage_source_entry`). A config's own real `sources:` entries (for
    tables NOT covered by `data`) are left untouched. `data=None` leaves
    `raw['sources']` alone entirely -- the config's own declared sources
    are used as-is, exactly like a plain `decoy run pipeline.yaml`."""
    if data is None:
        return
    sources = dict(raw.get("sources") or {})
    if isinstance(data, Mapping):
        items = list(data.items())
    else:
        name = _single_table_name(
            raw,
            require_columns=True,
            context="data was given as a single DataFrame/Table/path",
        )
        items = [(name, data)]
    for name, value in items:
        sources[name] = _stage_source_entry(name, value, tmp_paths)
    raw["sources"] = sources


def _apply_out_override(config_dict: dict, out: Any) -> None:
    """Merge `out` into `config_dict['targets']` so `_write_mask_outputs`
    (the CLI's own target writer) picks it up. `out=None` leaves whatever
    `targets:` the config already declared untouched -- a config carrying
    real target paths (e.g. a pipeline.yaml loaded as-is) still writes its
    files, exactly like `decoy run`."""
    if out is None:
        return
    targets = dict(config_dict.get("targets") or {})
    if isinstance(out, Mapping):
        for name, path in out.items():
            targets[name] = _file_target_entry(targets.get(name), path)
    else:
        name = _single_table_name(
            config_dict, require_columns=False, context="out=<path> is ambiguous"
        )
        targets[name] = _file_target_entry(targets.get(name), out)
    config_dict["targets"] = targets


def _file_target_entry(existing: Any, path: Any) -> dict:
    """Build (or update) a `FileTarget`-shaped dict for `path`. `format` is
    required by the engine's `TargetDescriptor` schema (no default), so it
    is inferred from the path suffix -- `.parquet`/`.pq` -> parquet,
    anything else -> csv -- unless `existing` already set one."""
    entry = dict(existing) if isinstance(existing, dict) else {}
    entry["path"] = str(path)
    entry.setdefault("type", "file")
    if "format" not in entry:
        suffix = Path(str(path)).suffix.lower()
        entry["format"] = "parquet" if suffix in (".parquet", ".pq") else "csv"
    return entry


def mask(
    data: Any = None,
    config: Any = None,
    *,
    mask_secret: str | None = None,
    master_key: str | bytes | None = None,
    key_label: str | None = None,
    out: Any = None,
    substrate: str | None = None,
) -> "pd.DataFrame | dict[str, pd.DataFrame]":
    """Mask (or generate) data through the same engine path `decoy run` uses.

    Wraps `decoy_engine.run_pipeline` -- the unified entry point `decoy run`
    calls for non-chunked runs (profiles, compiles, and executes mask +
    generate tables in one call). Mirrors `decoy run`'s semantics exactly:
    same determinism, same keyed-secret fail-closed gate (`mask_secret` /
    `global_settings.mask_secret_ref` -- see `decoy explain keys`), same
    config validation (`PipelineConfig`).

    Args:
        data: The source data. One of:
            - `None` (default): load sources from the config's own
              `sources:` block, exactly like `decoy run pipeline.yaml`.
            - A `pandas.DataFrame` or `pyarrow.Table`: used as the single
              mask-kind table's source. Only valid when the config declares
              exactly one mask-kind table (a `columns:` table).
            - A path (str/Path) to a CSV or Parquet file: same
              single-table rule as above.
            - A `dict[str, DataFrame | Table]` keyed by table name: for
              multi-table configs.
        config: The pipeline config, shaped exactly like the YAML `decoy
            run` consumes (`version`, `global_settings`, `tables`,
            `targets`, ...). Either a path (str/Path) to a YAML file, or an
            equivalent dict.
        mask_secret: `env:NAME` or `file:/PATH` reference to a >=32-byte
            mask secret, for keyed masking (fpe/hash/date_shift/...). Same
            slot as `global_settings.mask_secret_ref`; set at most one.
        master_key: 32-byte key (bytes, or hex str/`0x`-prefixed hex str)
            for keyed deterministic SYNTHETIC GENERATION (`generate_columns:`
            only -- independent of `mask_secret`). Requires `key_label`.
        key_label: Stable namespace string for `master_key`. Required when
            `master_key` is set.
        out: Where to write masked/generated output. `None` (default)
            writes whatever `targets:` the config already declares (or
            nothing, if it declares none). A path overrides the single
            declared table's target path. A `dict[str, path]` overrides
            per table by name.
        substrate: Execution substrate override (`"pandas"` or `"polars"`).
            `None` keeps `run_pipeline`'s default.

    Returns:
        The masked/generated table as a `pandas.DataFrame`, when the
        result covers exactly one table. A `dict[str, pandas.DataFrame]`
        keyed by table name otherwise.

    Raises:
        ConfigValidationError: the config fails `PipelineConfig` schema
            validation.
        MaskSecretConfigError: a mask secret is missing, malformed, or
            configured in two places at once.
        ValueError / TypeError: an ambiguous or wrongly-shaped `data` /
            `out` argument.

    Does NOT support `--chunked` streaming (`run_mask_pipeline_chunked`);
    that path exists for datasets too large to load into memory, which is
    orthogonal to an in-memory one-liner. Use the CLI directly for that.
    """
    if config is None:
        raise TypeError("config is required (a pipeline YAML path or a config dict).")

    from decoy_engine import PipelineConfig, run_pipeline
    from decoy_engine import __version__ as engine_version
    from pydantic import ValidationError as _PydanticValidationError

    raw = _load_config_dict(config)
    _validate_mask_secret_ref_shape(raw)

    tmp_paths: list[Path] = []
    try:
        # `data` must be staged into `sources` BEFORE PipelineConfig
        # validation: run_pipeline unconditionally profiles from the
        # config's declared `sources:` paths (see `_stage_source_entry`),
        # so a DataFrame/Table `data` value needs a real temp file before
        # validation ever runs, not just an in-memory override.
        _stage_data_sources(raw, data, tmp_paths)

        # `out` must be merged into `targets` BEFORE PipelineConfig
        # validation: the schema requires >=1 target (every pipeline
        # declares an explicit output, mirroring how sources are explicit
        # -- see decoy_engine.config._pipeline's
        # `targets: Field(min_length=1)`), so a config with no `targets:`
        # of its own is only valid once `out=` fills it in. Applying the
        # merge post-validation would be too late: a target-less raw
        # config never reaches model_dump().
        _apply_out_override(raw, out)
        if not raw.get("targets"):
            raise ConfigValidationError(
                "config declares no targets and out= was not given. Every "
                "decoy pipeline needs at least one output target: pass "
                "out=<path> (single-table config) or out={'table': <path>, "
                "...} (multi-table), or add a targets: block to the config."
            )

        try:
            config_dict = PipelineConfig.model_validate(raw).model_dump()
        except _PydanticValidationError as exc:
            raise ConfigValidationError(str(exc)) from exc

        _apply_mask_secret(config_dict, mask_secret)

        base_dir = Path(config).parent if isinstance(config, (str, Path)) else Path.cwd()
        # Every `sources:` entry now points at a real file (the caller's
        # own declared path, or one of the temp files just staged), so the
        # CLI's own loader (`decoy.cli.run._load_sources_from_config`)
        # handles both cases uniformly -- identical to a plain
        # `decoy run pipeline.yaml`.
        sources = _load_sources_from_config(config_dict, base_dir)

        resolver = _build_generation_resolver(master_key, key_label)
        instance_locale = (config_dict.get("global_settings") or {}).get("default_locale")

        # run_pipeline's own `substrate` kwarg default ("pandas") is NOT
        # the same as passing `substrate=None` explicitly: `None` means
        # "defer to DECOY_SUBSTRATE / the engine's internal default"
        # (`resolve_substrate`), which resolves to "polars" when
        # DECOY_SUBSTRATE is unset -- the opposite of the CLI's plain-run
        # contract ("plain runs always use pandas; --substrate is only
        # consulted for --chunked runs"). Mirror the CLI exactly: omit the
        # kwarg entirely unless the caller explicitly chose a substrate.
        run_pipeline_kwargs: dict[str, Any] = {}
        if substrate is not None:
            run_pipeline_kwargs["substrate"] = substrate

        result = run_pipeline(
            config_dict,
            sources,
            engine_version=engine_version,
            derive_key=resolver,
            instance_default_locale=instance_locale,
            **run_pipeline_kwargs,
        )

        _write_mask_outputs(config_dict, result, base_dir)
    finally:
        for tmp_path in tmp_paths:
            tmp_path.unlink(missing_ok=True)

    outputs = {name: table.to_pandas() for name, table in result.outputs.items()}
    if len(outputs) == 1:
        return next(iter(outputs.values()))
    return outputs


def scan(
    data: Any,
    *,
    source_label: str | None = None,
    rows: int | None = None,
    strategy: str = "head",
    format: str | None = None,
    layout: Any = None,
):
    """Profile a dataset for PII / re-identification risk, through the same
    engine path `decoy storm analyze` uses.

    Wraps `decoy_engine.run_storm` -- exactly what `decoy storm analyze`
    calls after loading the source into a DataFrame.

    Args:
        data: A `pandas.DataFrame`, or a path (str/Path) to a CSV, Parquet,
            or fixed-width file.
        source_label: Label recorded on the returned profile. Defaults to
            `"<dataframe>"` for in-memory data, or the file name for a path.
        rows: Sample row cap. `None` (default) scans everything.
        strategy: Sampling strategy when `rows` is set: `"full"`, `"head"`
            (default), or `"random"`.
        format: Input format for a path: `"delimited"` (CSV/TSV, default),
            `"parquet"`, or `"fixed-width"`. Inferred from the file
            extension when omitted. Ignored for DataFrame input.
        layout: Column layout for `format="fixed-width"`: a path (str/Path)
            to a YAML/JSON layout spec, or the already-parsed `columns`
            list (`[{"name": ..., "start": ..., "width": ...}, ...]`).

    Returns:
        A `decoy_engine.StormProfile` -- the same object `decoy storm
        analyze` serializes to `scan_<timestamp>.json`. Call `.to_dict()`
        for the JSON-ready shape.
    """
    from decoy_engine import run_storm

    try:
        strategy_enum = SampleStrategy(strategy)
    except ValueError as exc:
        valid = [s.value for s in SampleStrategy]
        raise ValueError(f"strategy must be one of {valid!r}, got {strategy!r}.") from exc

    if isinstance(data, pd.DataFrame):
        df = data
        if rows is not None and strategy_enum is not SampleStrategy.full:
            if strategy_enum is SampleStrategy.head:
                df = df.head(rows)
            elif strategy_enum is SampleStrategy.random and len(df) > rows:
                df = df.sample(n=rows, random_state=42).reset_index(drop=True)
        label = source_label or "<dataframe>"
    elif isinstance(data, (str, Path)):
        path = Path(data)
        fmt = InputFormat(format) if format is not None else _storm_infer_format(path)
        layout_columns: list[dict] | None
        if isinstance(layout, list):
            layout_columns = layout
        elif layout is not None:
            layout_columns = _parse_layout(Path(layout))
        else:
            layout_columns = None
        df = _load_data(path, fmt, layout_columns, rows, strategy_enum)
        label = source_label or path.name
    else:
        raise TypeError(
            f"data must be a pandas DataFrame or a path (str/Path), got {type(data).__name__}."
        )

    return run_storm(
        df,
        source_label=label,
        sample_strategy=strategy_enum.value,
        sample_row_cap=rows,
    )
