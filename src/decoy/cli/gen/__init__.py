"""Generation helpers for the CLI: the shared fit, the `run --rows` preview, the CSV scaffold and the `explain generation` text.

Commands import from this package, never from its `_` modules.
"""

from decoy.cli.gen._fit import (
    FIT_SAMPLE_SEED,
    ExactFit,
    FitSourceError,
    fit_exact_snapshot,
    read_fit_csv,
    strict_csv,
)
from decoy.cli.gen._preview import (
    RAISE_ROWS_HINT,
    ROWS_MAX,
    ROWS_MIN,
    refusal,
    render_preview,
    sample_tables,
    scale_row_counts,
)
from decoy.cli.gen._scaffold import scaffold_generate
from decoy.cli.gen._topic import generation_body, generation_info

__all__ = [
    "FIT_SAMPLE_SEED",
    "RAISE_ROWS_HINT",
    "ROWS_MAX",
    "ROWS_MIN",
    "ExactFit",
    "FitSourceError",
    "fit_exact_snapshot",
    "generation_body",
    "generation_info",
    "read_fit_csv",
    "refusal",
    "render_preview",
    "sample_tables",
    "scaffold_generate",
    "scale_row_counts",
    "strict_csv",
]
