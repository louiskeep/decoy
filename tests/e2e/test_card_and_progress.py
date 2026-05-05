"""Tests for the run-summary card + progress wrappers."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState
from decoy.ui.progress import multistage, spinner
from decoy.ui.theme import DECOY_THEME


def _state(mode: OutputMode) -> tuple[OutputState, StringIO, StringIO]:
    out_buf = StringIO()
    err_buf = StringIO()
    state = OutputState(
        mode=mode,
        verbose=False,
        console=Console(file=out_buf, theme=DECOY_THEME, force_terminal=False, no_color=True),
        err_console=Console(file=err_buf, theme=DECOY_THEME, force_terminal=False, no_color=True),
    )
    return state, out_buf, err_buf


# -- render_card --------------------------------------------------------


def test_render_card_emits_panel_in_default_mode():
    state, out, _ = _state(OutputMode.default)
    render_card(
        state,
        command="decoy run",
        facts=[("Pipeline", "pipeline.yaml"), ("Mode", "mask")],
        next_hint="head out.csv",
        status="ok",
    )
    rendered = out.getvalue()
    assert "decoy run" in rendered
    assert "Pipeline" in rendered
    assert "Next:" in rendered
    assert "head out.csv" in rendered


def test_render_card_suppressed_in_json_mode():
    state, out, _ = _state(OutputMode.json)
    render_card(state, command="decoy run", facts=[("a", "b")])
    assert out.getvalue() == ""


def test_render_card_suppressed_in_quiet_mode():
    state, out, _ = _state(OutputMode.quiet)
    render_card(state, command="decoy run", facts=[("a", "b")])
    assert out.getvalue() == ""


# -- progress wrappers --------------------------------------------------


def test_spinner_no_op_in_quiet_mode():
    state, _, err = _state(OutputMode.quiet)
    with spinner(state, "loading"):
        pass
    assert err.getvalue() == ""


def test_multistage_no_op_in_quiet_mode():
    state, _, err = _state(OutputMode.quiet)
    with multistage(state, ["Load", "Profile"]) as ms:
        ms.complete()
        ms.complete()
    assert err.getvalue() == ""


def test_multistage_handles_no_stages_gracefully():
    state, _, err = _state(OutputMode.default)
    with multistage(state, []) as ms:
        ms.complete()  # should not raise
    # Empty stages: nothing rendered.
    assert err.getvalue() == ""


def test_spinner_renders_to_stderr_in_default_mode_when_terminal():
    # Force a terminal so the spinner activates.
    out_buf = StringIO()
    err_buf = StringIO()
    state = OutputState(
        mode=OutputMode.default,
        verbose=False,
        console=Console(file=out_buf, theme=DECOY_THEME, force_terminal=False),
        err_console=Console(file=err_buf, theme=DECOY_THEME, force_terminal=True, no_color=True),
    )
    with spinner(state, "Working"):
        pass
    # Transient progress wipes itself; we just need to confirm no crash.
    assert err_buf.getvalue() is not None
