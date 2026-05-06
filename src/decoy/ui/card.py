"""Run-summary card -- the Panel printed after a meaningful command finishes.

See CLI_UX_GUIDE.md section 8. Card renders only in default (TTY) mode --
suppressed by --json (structured output covers it) and --quiet.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.theme import code, error, hint, success, warn


_STATUS_GLYPHS = {
    "ok": ("v", "success"),
    "warn": ("!", "warn"),
    "error": ("x", "error"),
}


def render_card(
    state: OutputState,
    *,
    command: str,
    facts: list[tuple[str, str]],
    next_hint: str | None = None,
    status: str = "ok",
) -> None:
    """Print a run-summary Panel to stdout.

    `facts` is a list of (label, value) pairs rendered as a two-column body.
    `next_hint` becomes the `Next:` line at the bottom. `status` is "ok" /
    "warn" / "error" -- decides the leading glyph.
    """
    if state.mode in (OutputMode.json, OutputMode.quiet):
        return

    glyph, glyph_token = _STATUS_GLYPHS.get(status, _STATUS_GLYPHS["ok"])
    if glyph_token == "success":
        title_glyph: Text = success(glyph)
    elif glyph_token == "warn":
        title_glyph = warn(glyph)
    else:
        title_glyph = error(glyph)

    title = Text.assemble(title_glyph, " ", (command, "accent"))

    body = Table.grid(padding=(0, 2))
    body.add_column(style="info", no_wrap=True)
    body.add_column(style="info")
    for label, value in facts:
        body.add_row(label, code(value))

    if next_hint:
        body.add_row("", "")
        body.add_row(hint("Next:"), code(next_hint))

    state.console.print(Panel(body, title=title, title_align="left", border_style="accent"))
