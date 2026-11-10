"""Write every table the CLI produces, by the format its target declares.

A target is written by its declared `format`, never inferred from the path. The one
exception is a vault-reversal output (`decoy unmask -o`, `decoy detokenize -o`), which
has no declaration and takes its format from the suffix through `format_for_path`.
A declared format that contradicts the path suffix is refused before any source is read.

This module holds every CLI table write, whole (`write_table`) and chunked
(`write_chunked_output`), so one sentry can keep it that way. It also decides which format a
CLI-written file is read back in (`input_format`, `entry_format`); the read calls themselves
stay in `cli/_sources.py`.

Source patterns: `cli/_sources.py` for the shape, and the platform's
`api/jobs/fixed_width_output.py` for the fixed-width frame conversion.
"""

from __future__ import annotations

import itertools
import math
import numbers
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pyarrow as pa

from decoy._atomic import staged_local_target, staged_private_target
from decoy.cli._sources import resolve_path
from decoy.cli.io._compression import csv_compression, is_archive_csv, split_compression
from decoy.cli.io._layout import owning_run, placed_path, same_path

if TYPE_CHECKING:
    import pandas as pd

SUFFIX_MISMATCH = "target_format_suffix_mismatch"
STREAMING_UNSUPPORTED = "target_format_streaming_unsupported"
FORMAT_UNKNOWN = "target_format_unknown"
UNREADABLE = "target_format_unreadable"

_FORMATS = ("csv", "parquet", "fixed_width")
_SUFFIX_FORMAT = {".csv": "csv", ".parquet": "parquet", ".pq": "parquet"}
_EXHAUSTED = object()  # a yielded chunk is never mistaken for the end
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1
_CANONICAL_INT = re.compile(r"0|-?[1-9][0-9]*")
_STREAMING_REFUSAL = (
    "--chunked cannot write a fixed_width target or a CSV inside a zip or tar archive; "
    "run without --chunked"
)


class TargetFormatError(ValueError):
    """A target the CLI refuses to write. The message never holds a path or a value."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TargetFormatIssue:
    """The non-raising form of `TargetFormatError`, for the config gate."""

    table: str
    code: str
    message: str


def _uncompressed_only_message(label: str, fmt: str, path: Path) -> str | None:
    """Message for a Parquet or fixed-width file under a compression suffix, else None.

    Those writers never compress, so a `.gz` name would hold an uncompressed file.
    """
    if fmt == "csv":
        return None
    name = path.name.lower()
    stem, method = split_compression(path)
    if method is None:
        return None
    return (
        f"{label}: declared format '{fmt}' cannot be written under the compression "
        f"suffix '{name[len(stem) :]}'; rename the file or change the format"
    )


def check_output_path(path: Path) -> None:
    """Refuse a vault-reversal output (`-o`) whose suffix the writer cannot honour."""
    message = _uncompressed_only_message("output", format_for_path(path), path)
    if message is not None:
        raise TargetFormatError(SUFFIX_MISMATCH, message)


def _format_suffix(path: Path) -> str:
    return Path(split_compression(path)[0]).suffix


def claimed_format(path: Path) -> str | None:
    """The format the suffix before any compression suffix claims: csv, parquet or None."""
    return _SUFFIX_FORMAT.get(_format_suffix(path))


def format_for_path(path: Path) -> str:
    """The format of a file with no declaration: parquet for `.parquet`/`.pq`, else csv."""
    return claimed_format(path) or "csv"


def _entry_issue(
    table: str, entry: Mapping[str, Any], *, chunked: bool
) -> TargetFormatIssue | None:
    fmt = entry.get("format")
    if not isinstance(fmt, str) or fmt not in _FORMATS:
        return TargetFormatIssue(
            table,
            FORMAT_UNKNOWN,
            f"targets.{table}: unsupported target format; expected csv, parquet or fixed_width",
        )
    path = Path(entry["path"])
    claimed = claimed_format(path)
    if claimed is not None and claimed != fmt:
        return TargetFormatIssue(
            table,
            SUFFIX_MISMATCH,
            f"targets.{table}: declared format '{fmt}' does not match the path suffix "
            f"'{_format_suffix(path)}'; rename the file or change the format",
        )
    message = _uncompressed_only_message(f"targets.{table}", fmt, path)
    if message is not None:
        return TargetFormatIssue(table, SUFFIX_MISMATCH, message)
    if chunked and (fmt == "fixed_width" or is_archive_csv(fmt, path)):
        return TargetFormatIssue(
            table,
            STREAMING_UNSUPPORTED,
            f"targets.{table}: --chunked cannot stream declared format '{fmt}' to this "
            "path (fixed_width, or CSV in a zip or tar archive); run without --chunked",
        )
    return None


def target_format_issues(config_dict: dict, *, chunked: bool) -> list[TargetFormatIssue]:
    """Every contradiction in the file targets, in sorted table order. Raises nothing.

    Cloud targets and entries without a path are skipped: `_require_local_io_endpoints`
    owns the first, and the writers skip the second.
    """
    targets = config_dict.get("targets") or {}
    if not isinstance(targets, dict):
        return []
    issues = []
    for name, entry in sorted(targets.items(), key=lambda item: str(item[0])):
        table = str(name)
        if not isinstance(entry, dict) or entry.get("type", "file") != "file":
            continue
        if not isinstance(entry.get("path"), str):
            continue
        issue = _entry_issue(table, entry, chunked=chunked)
        if issue is not None:
            issues.append(issue)
    return issues


def check_target_formats(config_dict: dict, *, chunked: bool) -> None:
    """Raise `TargetFormatError` for the first issue, before any table is read or written."""
    issues = target_format_issues(config_dict, chunked=chunked)
    if not issues:
        return
    first = issues[0]
    message = first.message
    if first.code == STREAMING_UNSUPPORTED:
        message = "; ".join(i.message for i in issues if i.code == STREAMING_UNSUPPORTED)
    raise TargetFormatError(first.code, message)


def resolve_target_format(table: str, entry: Mapping[str, Any]) -> str:
    """The declared format of one target to write, after the suffix contradiction check.

    The only function that reads a target's `format` for a write.
    """
    issue = _entry_issue(table, entry, chunked=False)
    if issue is not None:
        raise TargetFormatError(issue.code, issue.message)
    return str(entry["format"])


def _legacy_format_for_path(path: Path) -> str:
    """The format the pre-CLI-FMT writer gave a path: `.parquet` was Parquet, all else CSV.

    Not `format_for_path`: the old writer put CSV bytes into a `.pq` path.
    """
    return "parquet" if path.suffix.lower() == ".parquet" else "csv"


def _unreadable(fmt: object, layout: object) -> TargetFormatError | None:
    if not isinstance(fmt, str) or fmt not in _FORMATS:
        return TargetFormatError(UNREADABLE, "the file's format cannot be determined")
    if fmt == "fixed_width" and (not isinstance(layout, Mapping) or not layout):
        return TargetFormatError(UNREADABLE, "the file's format cannot be determined")
    return None


def _is_declared_target(
    path: Path, raw: str, base_dir: Path, pipeline: tuple[Path, str] | None
) -> bool:
    """True when `path` is the target declared as `raw`, at the old place or in a run folder."""
    if same_path(path, resolve_path(raw, base_dir)):
        return True
    if pipeline is None:
        return False
    run = owning_run(path, *pipeline)
    placed = placed_path(run, raw) if run is not None else None
    return placed is not None and same_path(path, placed)


def input_format(
    config_dict: Mapping[str, Any],
    table: str,
    path: Path,
    base_dir: Path,
    pipeline: tuple[Path, str] | None = None,
) -> tuple[str, Mapping[str, Any] | None]:
    """The format and layout to read a CLI-written file in, for `detokenize` and `unmask`.

    When `path` is the table's file target (both sides fully resolved), the target's declared
    format and layout apply, and an undeclared or unknown format is refused before any read.
    The target is the file at the old place (declared path against `base_dir`) or, when
    `pipeline` (project root, pipeline name) is given, the same declared path inside a run
    folder of that pipeline.
    Any other path has no declaration and takes the suffix rule.
    """
    targets = config_dict.get("targets")
    entry = targets.get(table) if isinstance(targets, Mapping) else None
    if (
        isinstance(entry, Mapping)
        and entry.get("type", "file") == "file"
        and isinstance(entry.get("path"), str)
        and _is_declared_target(path, entry["path"], base_dir, pipeline)
    ):
        layout = entry.get("layout")
        error = _unreadable(entry.get("format"), layout)
        if error is not None:
            raise error
        fmt = str(entry["format"])
        return fmt, layout if fmt == "fixed_width" else None
    return format_for_path(path), None


def entry_format(entry: Mapping[str, Any]) -> tuple[str, Mapping[str, Any] | None]:
    """The format and layout to read one evidence-manifest output entry in.

    An entry without `format` comes from a manifest written before CLI-FMT and takes the
    legacy rule. An entry whose format is unknown, or fixed_width without a layout, is refused.
    """
    path = Path(str(entry.get("path", "")))
    if "format" not in entry:
        return _legacy_format_for_path(path), None
    layout = entry.get("layout")
    error = _unreadable(entry["format"], layout)
    if error is not None:
        raise error
    fmt = str(entry["format"])
    return fmt, layout if fmt == "fixed_width" else None


def _coerce_canonical_int_strings(series: pd.Series) -> pd.Series | None:
    """Strings that are canonical int64 digits become Int64; anything else stays as is.

    A CSV source reads every cell as text. No value changes: a leading zero, `-0`, a
    sign, spaces, a trailing newline or an out-of-range number leaves the column alone,
    so the writer refuses it.
    """
    import pandas as pd

    present = series.dropna()
    for value in present:
        if not isinstance(value, str) or _CANONICAL_INT.fullmatch(value) is None:
            return None
        if not _INT64_MIN <= int(value) <= _INT64_MAX:
            return None
    return pd.Series(
        [pd.NA if pd.isna(v) else int(v) for v in series],
        index=series.index,
        dtype="Int64",
        name=series.name,
    )


def _is_integral_in_range(value: float) -> bool:
    return math.isfinite(value) and value == math.floor(value) and _INT64_MIN <= value <= _INT64_MAX


def _coerce_object_series(series: pd.Series) -> pd.Series | None:
    """Python ints and integral floats only; bool, Decimal and str stay untouched."""
    import numpy as np
    import pandas as pd

    for value in series.dropna():
        if isinstance(value, (bool, np.bool_)):
            return None
        if isinstance(value, numbers.Integral):
            if not _INT64_MIN <= int(value) <= _INT64_MAX:
                return None
        elif isinstance(value, float):
            if not _is_integral_in_range(value):
                return None
        else:
            return None
    return pd.Series(
        [pd.NA if pd.isna(v) else int(v) for v in series],
        index=series.index,
        dtype="Int64",
        name=series.name,
    )


def _coerce_int_columns(frame: pd.DataFrame, layout: Mapping[str, Any]) -> pd.DataFrame:
    """Coerce float and object columns the layout types `int` to Int64, losslessly.

    Ported from the platform's `coerce_int_columns`: a column is touched only when every
    non-null value is finite, integral and in int64 range. Anything else is left for the
    engine writer to refuse. Object columns of strings also take the CLI-only canonical
    digit rule, because a CSV source arrives as text.
    """
    import pandas as pd

    out = frame.copy()
    for column in layout.get("columns") or []:
        if not isinstance(column, Mapping) or column.get("type") != "int":
            continue
        name = column.get("name")
        if name not in out.columns:
            continue
        series = out[name]
        dtype = series.dtype
        coerced: pd.Series | None = None
        if pd.api.types.is_bool_dtype(dtype):
            continue
        if pd.api.types.is_float_dtype(dtype):
            present = series.dropna()
            if all(_is_integral_in_range(float(v)) for v in present):
                coerced = series.astype("Int64")
        elif pd.api.types.is_object_dtype(dtype):
            coerced = _coerce_object_series(series)
            if coerced is None:
                coerced = _coerce_canonical_int_strings(series)
        if coerced is not None:
            out[name] = coerced
    return out


def _csv_frame(table: pa.Table) -> pd.DataFrame:
    """The one Arrow-to-pandas step before a CSV write.

    `Table.to_pandas()` turns an integer column that holds a null into float64, which prints
    `23.0` and loses `uint64` values above 2**53. The engine converter keeps each integer type
    as its pandas nullable dtype, so the cell text is the integer. Unlike `_coerce_int_columns`
    this never reads a layout: it keeps the type the table already has.
    """
    from decoy_engine import generated_table_to_pandas

    return generated_table_to_pandas(table)


def _write_fixed_width(table: pa.Table, layout: Mapping[str, Any] | None, path: Path) -> None:
    from decoy_engine import write_fixed_width

    if layout is None:
        raise TargetFormatError(FORMAT_UNKNOWN, "a fixed_width target needs a layout")
    frame = _coerce_int_columns(table.to_pandas(), layout)
    write_fixed_width(frame, dict(layout), path)


def _write_table(
    data: pa.Table | pd.DataFrame,
    fmt: str,
    path: Path,
    layout: Mapping[str, Any] | None,
    stage: Callable[[Path], AbstractContextManager[Path]],
) -> None:
    import pandas as pd
    import pyarrow.parquet as pq

    message = _uncompressed_only_message("output", fmt, path)
    if message is not None:
        raise TargetFormatError(SUFFIX_MISMATCH, message)
    frame = isinstance(data, pd.DataFrame)
    if fmt == "fixed_width":
        if frame:
            raise TypeError("write_table: fixed_width needs a pyarrow Table")
        _write_fixed_width(data, layout, path)
        return
    if fmt not in ("csv", "parquet"):
        raise TargetFormatError(FORMAT_UNKNOWN, "unsupported target format")
    compression = csv_compression(path)
    with stage(path) as tmp:
        if fmt == "csv":
            (data if frame else _csv_frame(data)).to_csv(tmp, index=False, compression=compression)
        elif frame:
            data.to_parquet(tmp, index=False)
        else:
            pq.write_table(data, str(tmp))


def write_table(
    data: pa.Table | pd.DataFrame,
    fmt: str,
    path: Path,
    layout: Mapping[str, Any] | None = None,
) -> None:
    """Write one whole table. The only whole-table writer in the CLI.

    CSV and Parquet are staged beside `path` and published only when the write finishes, so a
    failure keeps the old file. An existing file keeps its mode bits. Fixed width goes straight
    to the engine writer, which stages and publishes by itself.
    """
    _write_table(data, fmt, path, layout, staged_local_target)


def write_private_table(
    data: pa.Table | pd.DataFrame,
    fmt: str,
    path: Path,
    layout: Mapping[str, Any] | None = None,
) -> None:
    """`write_table` for restored original values (`unmask`, `detokenize`): owner-only (0600).

    Fixed width is refused: the engine writer stages by itself and would not apply 0600.
    """
    if fmt == "fixed_width":
        raise TargetFormatError(FORMAT_UNKNOWN, "a private output cannot be fixed_width")
    _write_table(data, fmt, path, layout, staged_private_target)


def write_targets(
    config_dict: dict, outputs: Mapping[str, pa.Table], base_dir: Path
) -> dict[str, Path]:
    """Write each declared file target from `outputs`, by its declared format.

    Callers run `check_target_formats` first so a contradiction is refused before the
    first table is written; this resolves each entry as it iterates. Returns table name to
    path for the files actually published: a path is added only after its write returns.
    """
    published: dict[str, Path] = {}
    targets = config_dict.get("targets") or {}
    if not isinstance(targets, dict):
        return published
    for table_name, entry in targets.items():
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        table = outputs.get(table_name)
        if table is None:
            continue
        fmt = resolve_target_format(str(table_name), entry)
        path = resolve_path(raw_path, base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_table(table, fmt, path, entry.get("layout"))
        published[str(table_name)] = path
    return published


def write_chunked_output(
    masked_iter: Iterable[pa.Table],
    fmt: str,
    out_path: Path,
    *,
    empty_schema: Callable[[], pa.Schema] | None,
) -> Path | None:
    """Stream masked chunks to `out_path` in `fmt`. The only chunked writer in the CLI.

    The chunks go to a staged temp beside `out_path`, published only after the last one, so
    a failure after chunk one keeps the old output. The first chunk is read before staging:
    an empty source that writes nothing leaves the old output alone and makes no temp.
    Returns `out_path` once the file is published, or None when nothing was published.
    """
    import pyarrow.parquet as pq

    if fmt not in ("csv", "parquet") or is_archive_csv(fmt, out_path):
        raise TargetFormatError(STREAMING_UNSUPPORTED, _STREAMING_REFUSAL)
    chunks = iter(masked_iter)
    first = next(chunks, _EXHAUSTED)
    schema = None
    if first is _EXHAUSTED:
        if fmt == "csv" or empty_schema is None:
            return None
        # Empty parquet source: emit a valid zero-row file with the source schema, matching
        # what a plain run writes. Read before staging so a schema error leaves no temp.
        schema = empty_schema()
    elif fmt == "parquet":
        schema = cast("pa.Table", first).schema
    with staged_local_target(out_path) as tmp:
        if fmt == "parquet":
            with pq.ParquetWriter(str(tmp), schema) as writer:
                for masked in () if first is _EXHAUSTED else itertools.chain((first,), chunks):
                    writer.write_table(masked)
        else:
            compression = csv_compression(out_path)
            for index, masked in enumerate(itertools.chain((first,), chunks)):
                _csv_frame(masked).to_csv(
                    tmp,
                    index=False,
                    header=index == 0,
                    mode="a" if index else "w",
                    compression=compression,
                )
    # Reached only after the staging context published the file.
    return out_path


def table_records(
    rows: Mapping[str, int | None], paths: Mapping[str, Path | None]
) -> list[dict[str, Any]]:
    """One `{name, rows, path}` record per table for the run summary.

    `rows` is None when the writer streamed and never counted; `path` is None when no file
    was published. Neither is ever inferred from the config.
    """
    return [
        {"name": name, "rows": count, "path": str(path) if path is not None else None}
        for name, count in rows.items()
        for path in (paths.get(name),)
    ]
