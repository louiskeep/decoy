"""Tests for the storm-themed multistage indicator."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.storm_animation import (
    HEADER_FRAMES,
    RUNNING_FRAMES,
    _StormyHandle,
    stormy_multistage,
)
from decoy.ui.theme import DECOY_THEME


def _state(
    mode: OutputMode, *, terminal: bool = False
) -> tuple[OutputState, StringIO, StringIO]:
    out_buf = StringIO()
    err_buf = StringIO()
    state = OutputState(
        mode=mode,
        verbose=False,
        console=Console(file=out_buf, theme=DECOY_THEME, force_terminal=False, no_color=True),
        err_console=Console(
            file=err_buf, theme=DECOY_THEME, force_terminal=terminal, no_color=True
        ),
    )
    return state, out_buf, err_buf


def test_stormy_multistage_no_op_in_quiet_mode():
    state, _, err = _state(OutputMode.quiet)
    with stormy_multistage(state, ["Load", "Profile"]) as ms:
        ms.complete()
        ms.complete()
    assert err.getvalue() == ""


def test_stormy_multistage_no_op_in_non_tty():
    state, _, err = _state(OutputMode.default, terminal=False)
    with stormy_multistage(state, ["Load", "Profile"]) as ms:
        ms.complete()
        ms.complete()
    assert err.getvalue() == ""


def test_stormy_multistage_handles_no_stages_gracefully():
    state, _, err = _state(OutputMode.default, terminal=True)
    with stormy_multistage(state, []) as ms:
        ms.complete()  # should not raise
    assert err.getvalue() == ""


def test_stormy_handle_renders_done_running_pending_in_order():
    """Direct render exercise -- no Live, no thread, just the build output."""
    handle = _StormyHandle(
        live=None, stages=["Load", "Profile", "Save"], frame_state={"frame": 0}
    )
    handle.complete()  # idx -> 1, so "Load" is done, "Profile" is running

    err_buf = StringIO()
    console = Console(file=err_buf, theme=DECOY_THEME, force_terminal=True, no_color=True)
    console.print(handle._build())
    out = err_buf.getvalue()

    # "Load" is done.
    assert "[v] Load" in out
    # "Profile" is running -- the icon is the frame-0 glyph.
    assert f"[{RUNNING_FRAMES[0]}] Profile" in out
    # "Save" is pending.
    assert "[ ] Save" in out
    # Header line is present.
    assert HEADER_FRAMES[0] in out


def test_running_and_header_frame_counts_match():
    """Frame indices are taken modulo each list -- they don't have to match in
    length, but if they ever drift we want a deliberate change, not an accident.
    """
    assert len(RUNNING_FRAMES) == len(HEADER_FRAMES)


def test_running_frames_are_ascii_only():
    """Per CLI_UX_GUIDE.md section 14 -- no Unicode in default output."""
    for frame in RUNNING_FRAMES:
        frame.encode("ascii")
    for header in HEADER_FRAMES:
        header.encode("ascii")
