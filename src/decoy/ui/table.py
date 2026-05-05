"""Rich Table styled with the decoy theme.

Use this instead of constructing Tables directly so headers/borders pick up
the `accent` token and stay consistent with the rest of the UI.
"""

from __future__ import annotations

from rich.box import SIMPLE
from rich.table import Table


def make_table(*columns: str, title: str | None = None) -> Table:
    """Build a Rich Table with theme-styled header + accent border."""
    table = Table(
        title=title,
        title_style="accent",
        header_style="accent",
        border_style="accent",
        box=SIMPLE,
        pad_edge=False,
        show_lines=False,
    )
    for col in columns:
        table.add_column(col)
    return table
