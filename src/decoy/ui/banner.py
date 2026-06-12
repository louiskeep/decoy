"""Decoy CLI banner -- the small branded panel rendered by `decoy info`.

Kept in `decoy.ui` so all rendering primitives live in one place. The
banner is ASCII-only per CLI_UX_GUIDE.md section 14 -- no box-drawing
characters or em-dashes baked into the text. Rich draws the border.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from decoy import __version__
from decoy.ui.output import OutputState
from decoy.ui.theme import code


_ASCII_LOGO = r"""
 ____
|  _ \ ___  ___ ___  _   _
| | | / _ \/ __/ _ \| | | |
| |_| |  __/ (_| (_) | |_| |
|____/ \___|\___\___/ \__, |
                      |___/
""".rstrip("\n")


_TAGLINE = "Data masking and synthetic generation from the terminal."


def render_banner(state: OutputState) -> None:
    """Print the branded banner Panel to stdout (default-mode only).

    Returns silently in --json or --quiet mode -- the banner is decorative.
    """
    from decoy.ui.output import OutputMode

    if state.mode is not OutputMode.default:
        return

    body = Table.grid(padding=(0, 0))
    body.add_column(no_wrap=True)
    body.add_row(Text(_ASCII_LOGO, style="accent"))
    body.add_row("")
    body.add_row(Text(_TAGLINE, style="info"))
    body.add_row("")

    quickstart = Table.grid(padding=(0, 1))
    quickstart.add_column(style="hint", no_wrap=True)
    quickstart.add_column()
    quickstart.add_row("First scan:", code("decoy storm scan data.csv"))
    quickstart.add_row("First run:", code("decoy demo"))
    quickstart.add_row("Scaffold:", code("decoy init"))
    quickstart.add_row("Topics:", code("decoy explain modes"))
    quickstart.add_row("Templates:", code("decoy templates list"))
    body.add_row(quickstart)

    title = Text.assemble(("decoy ", "accent"), (f"v{__version__}", "code"))
    state.console.print(
        Panel(body, title=title, title_align="left", border_style="accent")
    )
