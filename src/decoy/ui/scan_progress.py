"""Neutral multi-stage progress indicator for the `decoy pre-scan` / `post-scan` commands.

One line per stage; the active stage cycles a plain ASCII pulse. Output goes to
stderr and auto-disables in --quiet or a non-TTY (CLI_UX_GUIDE sections 7 and 14).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Group
from rich.live import Live

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.theme import accent, hint, success

# Pulse glyphs for the active stage; ASCII only.
RUNNING_FRAMES: list[str] = [".", "o", "O", "o"]

PENDING_ICON = " "
DONE_ICON = "v"

REFRESH_INTERVAL_S = 0.25


class _StageHandle:
    """Callers only touch `complete()` to advance to the next stage."""

    def __init__(self, live: Live | None, stages: list[str], frame_state: dict) -> None:
        self._live = live
        self._stages = stages
        self._frame_state = frame_state
        self._idx = 0

    def _build(self) -> Group:
        running_glyph = RUNNING_FRAMES[self._frame_state["frame"] % len(RUNNING_FRAMES)]
        lines: list = []
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
def scan_stages(state: OutputState, stages: list[str]) -> Iterator[_StageHandle]:
    """Multi-stage indicator with a per-stage pulse glyph."""
    if _disabled(state) or not stages:
        yield _StageHandle(None, stages, {"frame": 0})
        return

    frame_state: dict = {"frame": 0}
    stop_event = threading.Event()

    with Live(console=state.err_console, refresh_per_second=4, transient=True) as live:
        handle = _StageHandle(live, stages, frame_state)
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
