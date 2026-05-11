"""Storm-themed multi-stage indicator for `decoy storm scan`.

A fixed multi-line ASCII cumulus silhouette anchors the top of the scene;
eight rain/lightning frames cycle underneath. The per-stage running marker
cycles its own little glyph (~ ; * .) on the active stage. Cloud pops
yellow on the lightning beats, dim on the calm frames.

All ASCII per CLI_UX_GUIDE section 14; auto-disables in --quiet or non-TTY
per section 7.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from rich.console import Group
from rich.live import Live

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.theme import accent, hint, success, warn


# Cumulus silhouette -- two puffs, flat-ish base. Stays put across all
# frames so only the rain/lightning beneath it changes (the eye locks onto
# the cloud and reads the rain as motion).
_CLOUD_LINES: list[str] = [
    "         _.-~-._   _.-~-._         ",
    "      .-~      ~~-~      ~-.        ",
    "     :                      :       ",
    "      `.                  .'        ",
    "        `~-..__________..-~'        ",
]

# Rain / lightning area beneath the cloud -- 3 lines per frame so total
# scene height stays a fixed 8 lines and the stage list below never jumps.
_RAIN_FRAMES_RAW: list[list[str]] = [
    # Frame 0: calm sky -- no rain at all.
    [
        "                                   ",
        "                                   ",
        "                                   ",
    ],
    # Frame 1: first drops.
    [
        "              .                    ",
        "            .   .                  ",
        "                                   ",
    ],
    # Frame 2: gentle rain (dotted drops).
    [
        "         . . . . . . .             ",
        "        . . . . . . .              ",
        "         . . . . . . .             ",
    ],
    # Frame 3: heavy slanted rain (diagonal sheets).
    [
        "       / / / / / / /               ",
        "        / / / / / /                ",
        "       / / / / / / /               ",
    ],
    # Frame 4: LIGHTNING strikes from the left, rain still falling.
    [
        "       /' / / / / /                ",
        "      /  / / / / /                 ",
        "     V  / / / / /                  ",
    ],
    # Frame 5: LIGHTNING strikes from the right.
    [
        "       / / / / / '\\                ",
        "        / / / / /  \\               ",
        "        / / / / /   V               ",
    ],
    # Frame 6: DOUBLE STRIKE -- thunder rolls.
    [
        "       /'  / / /  '\\               ",
        "      /   / / /    \\               ",
        "     V    / / /     V               ",
    ],
    # Frame 7: storm passes -- last few drops.
    [
        "            . .                    ",
        "              .                    ",
        "                                   ",
    ],
]


# Cached as one string per frame -- joined once at module load.
CLOUD_FRAMES: list[str] = [
    "\n".join(_CLOUD_LINES + rain) for rain in _RAIN_FRAMES_RAW
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
        scene_idx = frame % len(CLOUD_FRAMES)
        running_glyph = RUNNING_FRAMES[frame % len(RUNNING_FRAMES)]
        is_lightning = scene_idx in _LIGHTNING_FRAMES

        scene_str = CLOUD_FRAMES[scene_idx]
        if is_lightning:
            scene = warn(scene_str)
        elif scene_idx == 0:
            scene = hint(scene_str)
        else:
            scene = accent(scene_str)

        lines: list = [scene]
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
