"""Tests for the neutral scan-progress multistage indicator."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from decoy.ui.output import OutputMode, OutputState
from decoy.ui.scan_progress import RUNNING_FRAMES, _StageHandle, scan_stages
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


def test_scan_stages_no_op_in_quiet_mode():
    state, _, err = _state(OutputMode.quiet)
    with scan_stages(state, ["Load", "Profile"]) as ms:
        ms.complete()
        ms.complete()
    assert err.getvalue() == ""


def test_scan_stages_no_op_in_non_tty():
    state, _, err = _state(OutputMode.default, terminal=False)
    with scan_stages(state, ["Load", "Profile"]) as ms:
        ms.complete()
        ms.complete()
    assert err.getvalue() == ""


def test_scan_stages_handles_no_stages_gracefully():
    state, _, err = _state(OutputMode.default, terminal=True)
    with scan_stages(state, []) as ms:
        ms.complete()  # should not raise
    assert err.getvalue() == ""


def test_stage_handle_renders_stages():
    """Direct render exercise -- no Live, no thread, just the build output."""
    handle = _StageHandle(live=None, stages=["Load", "Profile", "Save"], frame_state={"frame": 0})
    handle.complete()  # idx -> 1, so "Load" is done, "Profile" is running

    err_buf = StringIO()
    console = Console(file=err_buf, theme=DECOY_THEME, force_terminal=True, no_color=True)
    console.print(handle._build())
    out = err_buf.getvalue()

    assert "[v] Load" in out
    assert f"[{RUNNING_FRAMES[0]}] Profile" in out
    assert "[ ] Save" in out


def test_running_frames_are_ascii_only():
    """Per CLI_UX_GUIDE.md section 14 -- no Unicode in default output."""
    for frame in RUNNING_FRAMES:
        frame.encode("ascii")
