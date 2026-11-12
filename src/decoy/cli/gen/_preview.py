"""`decoy run --rows N`: scale a generate pipeline down and show what it would write.

Source pattern: `dbt show --limit` (same pipeline, few rows, nothing written). Every generate
table's `row_count` becomes `max(1, round(row_count * N / largest))`, so the largest table has
N rows and parent-to-child ratios hold; a flat N would break per-parent minimums on a small
parent. The run itself stays in `cli/run/`; this module holds the pure parts.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ROWS_MIN = 1
ROWS_MAX = 1000
RAISE_ROWS_HINT = "raise --rows so the scaled tables can meet the per-parent bound."


def refusal(rows: int, flags: Sequence[str], has_mask_table: bool) -> str | None:
    """Why `--rows` cannot run here, or None. Names flags and tables only."""
    if not ROWS_MIN <= rows <= ROWS_MAX:
        return f"--rows must be a whole number from {ROWS_MIN} to {ROWS_MAX}."
    if flags:
        return (
            "--rows previews generate tables and writes nothing, so it cannot be combined with "
            f"{', '.join(flags)}."
        )
    if has_mask_table:
        return (
            "--rows previews generate tables only and this pipeline has a mask table. "
            "Preview a pipeline with generate tables only."
        )
    return None


def scale_row_counts(raw: Any, rows: int) -> Any:
    """A copy of the raw config with every generate table scaled to the preview size.

    A config that is not a mapping, or has no generate row counts, comes back unchanged for the
    normal config check to report.
    """
    tables = raw.get("tables") if isinstance(raw, dict) else None
    if not isinstance(tables, list):
        return raw
    declared = [declared_rows(t) for t in tables]
    counts = [c for c in declared if c is not None]
    if not counts:
        return raw
    largest = max(counts)
    scaled = copy.deepcopy(raw)
    for table, count in zip(scaled["tables"], declared, strict=True):
        if count is not None:
            table["row_count"] = max(1, round(count * rows / largest))
    return scaled


def declared_rows(table: Any) -> int | None:
    """The declared `row_count` of a generate table; None for anything else."""
    if not isinstance(table, dict) or not table.get("generate_columns"):
        return None
    count = table.get("row_count")
    return count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else None


def sample_tables(
    outputs: Mapping[str, Any], order: Iterable[str], rows: int
) -> list[dict[str, Any]]:
    """Each output table's name, row count, column names and first `rows` rows, in `order`."""
    names = [n for n in order if n in outputs]
    names += [n for n in outputs if n not in names]
    out = []
    for name in names:
        table = outputs[name]
        sample = json.loads(json.dumps(table.slice(0, rows).to_pylist(), default=str))
        out.append(
            {
                "name": name,
                "rows": len(table),
                "columns": list(table.column_names),
                "sample": sample,
            }
        )
    return out


def render_preview(state: Any, tables: Sequence[dict[str, Any]]) -> None:
    """Print each table's rows under its name (human mode only)."""
    from rich.text import Text

    from decoy.ui.output import OutputMode
    from decoy.ui.table import make_table
    from decoy.ui.theme import hint

    if state.mode is not OutputMode.default:
        return
    state.console.print(hint("preview: scaled-down run, nothing was written."))
    for entry in tables:
        state.console.print()
        state.console.print(Text(f"{entry['name']} ({entry['rows']} rows)"))
        grid = make_table(*entry["columns"])
        for row in entry["sample"]:
            grid.add_row(*(Text(_cell(row.get(c))) for c in entry["columns"]))
        state.console.print(grid)


def _cell(value: Any) -> str:
    return "" if value is None else str(value)
