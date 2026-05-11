"""Storm-themed multi-stage indicator for `decoy storm scan`.

Same surface as `decoy.ui.progress.multistage` -- only the running-stage
icon swaps from a static `[*]` to a cycling ASCII weather glyph, plus a
one-line forecast header above the stages. Lives here (not in progress.py)
because it is storm-specific theming; no other command should reach for it.

Per CLI_UX_GUIDE.md sections 7 + 13 + 14: ASCII-only output, the cycling
glyph still serves the same communicative purpose as multistage's `[*]`
(this stage is the active one), auto-disabled in --quiet or non-TTY.
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


# ASCII weather frames. The running-stage icon and the header line share a
# monotonic frame counter so they stay in phase.
RUNNING_FRAMES: list[str] = ["~", ";", "*", "."]
HEADER_FRAMES: list[str] = [
    "clouds gathering...",
    "rain falling.......",
    "lightning strikes!.",
    "storm passing......",
]

PENDING_ICON = " "
DONE_ICON = "v"

# Quarter-second cadence: fast enough to read as motion, slow enough that
# the `*` lightning frame doesn't strobe.
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
        running_glyph = RUNNING_FRAMES[frame % len(RUNNING_FRAMES)]
        header_text = HEADER_FRAMES[frame % len(HEADER_FRAMES)]
        is_lightning = running_glyph == "*"

        # Header pops yellow on the lightning frame, cyan otherwise.
        header = warn(header_text) if is_lightning else accent(header_text)
        lines: list[Text] = [header]

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
    """Multi-stage indicator with cycling weather glyphs on the running stage.

    Drop-in replacement for `multistage()` for the `storm scan` command. The
    handle exposes the same `complete()` so callers can swap freely.
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
