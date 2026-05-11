"""Storm-themed multi-stage indicator for `decoy storm scan`.

Bigger version: a multi-line ASCII storm cloud cycles above the stages, a
narrative header line tracks the scene, and the per-stage running marker
cycles a small weather glyph in place of the static `[*]`. All ASCII per
CLI_UX_GUIDE section 14; auto-disables in --quiet or non-TTY per section 7.

The cloud and the per-stage glyph index off the same monotonic frame
counter modulo their respective lengths -- they don't have to match in
count, just the cloud + header lengths do (they ride together).
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from rich.console import Group
from rich.live import Live
from rich.text import Text

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.theme import accent, hint, success, warn


# 8 multi-line ASCII storm scenes. Each frame is exactly 7 lines tall and
# 30 chars wide so the stage list below stays anchored.
_CLOUD_FRAMES_RAW: list[list[str]] = [
    # Frame 0: calm sky
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "                              ",
        "                              ",
        "                              ",
    ],
    # Frame 1: first drops
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "        '          '          ",
        "                              ",
        "                              ",
    ],
    # Frame 2: steady rain
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "        '   '   '             ",
        "          '   '   '           ",
        "        '   '   '             ",
    ],
    # Frame 3: the heavens open
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "      ' ' ' ' ' ' '           ",
        "       ' ' ' ' ' '            ",
        "      ' ' ' ' ' ' '           ",
    ],
    # Frame 4: LIGHTNING from the left
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "       /' '  ' ' '            ",
        "      / ' ' ' ' '             ",
        "     *  ' ' ' ' '             ",
    ],
    # Frame 5: LIGHTNING from the right
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "       ' '  ' ' '\\           ",
        "        ' ' ' ' ' \\           ",
        "        ' ' ' ' '  *           ",
    ],
    # Frame 6: DOUBLE STRIKE -- thunder rages
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "       /' ' ' ' '\\           ",
        "      / ' ' ' ' ' \\           ",
        "     *  ' ' ' ' '  *           ",
    ],
    # Frame 7: storm passes
    [
        "                              ",
        "       .--.    .-.            ",
        "    .-(    )--(   )-.         ",
        "   (___.__)__)___..-'         ",
        "        '       '             ",
        "           '                  ",
        "                              ",
    ],
]

CLOUD_FRAMES: list[str] = ["\n".join(lines) for lines in _CLOUD_FRAMES_RAW]

# Narrative header -- one phrase per cloud frame, padded to a consistent
# width so the layout doesn't twitch as the text changes.
HEADER_FRAMES: list[str] = [
    "  skies clear...........",
    "  first drops fall......",
    "  rain steadies.........",
    "  the heavens open......",
    "  ** LIGHTNING **.......",
    "  ** THUNDER CRACKS **..",
    "  ** STORM RAGES **.....",
    "  the storm passes......",
]

# Per-stage running marker -- cycles independently to give the active
# stage a small pulse beneath the bigger cloud animation.
RUNNING_FRAMES: list[str] = ["~", ";", "*", "."]

# Frame indices that should render in `warn` (yellow) -- the lightning beats.
_LIGHTNING_FRAMES: frozenset[int] = frozenset({4, 5, 6})

PENDING_ICON = " "
DONE_ICON = "v"

# Quarter-second cadence keeps motion fluid without strobing the lightning.
REFRESH_INTERVAL_S = 0.25


class _StormyHandle:
    """Mirrors `_MultistageHandle` -- callers only touch `complete()`."""

    def __init__(
        self,
        live: Live | None,
        stages: list[str],
        frame_state: dict,
    ) -> None:
        self._live = live
        self._stages = stages
        self._frame_state = frame_state
        self._idx = 0

    def _build(self) -> Group:
        frame = self._frame_state["frame"]
        cloud_idx = frame % len(CLOUD_FRAMES)
        running_glyph = RUNNING_FRAMES[frame % len(RUNNING_FRAMES)]
        header_text = HEADER_FRAMES[cloud_idx]
        is_lightning = cloud_idx in _LIGHTNING_FRAMES

        cloud_str = CLOUD_FRAMES[cloud_idx]
        if is_lightning:
            cloud = warn(cloud_str)
            header: Text = warn(header_text)
        elif cloud_idx == 0:
            cloud = hint(cloud_str)
            header = hint(header_text)
        else:
            cloud = accent(cloud_str)
            header = accent(header_text)

        lines: list = [cloud, header]
        for i, label in enumerate(self._stages):
            if i < self._idx:
                lines.append(success(f"[{DONE_ICON}] {label}"))
            elif i == self._idx:
                lines.append(accent(f"[{running_glyph}] {label}"))
            else:
                lines.append(hint(f"[{PENDING_ICON}] {label}"))
        return Group(*lines)

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._build())

    def complete(self) -> None:
        self._idx += 1
        self.refresh()


def _disabled(state: OutputState) -> bool:
    return state.mode is OutputMode.quiet or not state.err_console.is_terminal


@contextmanager
def stormy_multistage(
    state: OutputState, stages: list[str]
) -> Iterator[_StormyHandle]:
    """Multi-stage indicator with a big cycling storm cloud + per-stage glyph.

    Drop-in replacement for `multistage()` for the `storm scan` and
    `storm test` commands. The handle exposes the same `complete()` so
    callers can swap freely.
    """
    if _disabled(state) or not stages:
        yield _StormyHandle(None, stages, {"frame": 0})
        return

    frame_state: dict = {"frame": 0}
    stop_event = threading.Event()

    with Live(
        console=state.err_console,
        refresh_per_second=4,
        transient=True,
    ) as live:
        handle = _StormyHandle(live, stages, frame_state)
        handle.refresh()

        def _spin() -> None:
            while not stop_event.wait(REFRESH_INTERVAL_S):
                frame_state["frame"] += 1
                handle.refresh()

        thread = threading.Thread(target=_spin, daemon=True)
        thread.start()
        try:
            yield handle
        finally:
            stop_event.set()
            thread.join(timeout=1.0)
