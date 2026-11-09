"""AT-S1: no Python traceback reaches a user, whatever a command raises.

`decoy.__main__._GuardedGroup.invoke` is the one choke point. It turns an unexpected
`Exception` into `error: internal error (<ClassName>)` with exit 1, re-raises under
`DECOY_DEBUG=1`, and lets the control-flow exceptions Click and Typer already handle
(`typer.Exit`, `typer.Abort`, usage errors, `EOFError`, EPIPE) through untouched.

The cells build a fresh `Typer(cls=_GuardedGroup)` with a callback and two commands (a
one-command app ignores `cls`), then run the real root app for the usage-error exits.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys

import pytest
import typer
from typer.testing import CliRunner

from decoy.__main__ import _USAGE_ERROR, _GuardedGroup, app

CANARY = "CANARY-123"
runner = CliRunner()
# Read at import, after tests/conftest.py ran and before any cell clears it.
_DEBUG_AT_COLLECTION = os.environ.get("DECOY_DEBUG")


@pytest.fixture(autouse=True)
def _debug_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    # tests/conftest.py sets DECOY_DEBUG=1 for the whole suite; the guard's own cells need the
    # production default.
    monkeypatch.delenv("DECOY_DEBUG", raising=False)


def _guarded(exc: BaseException) -> typer.Typer:
    guarded = typer.Typer(cls=_GuardedGroup, pretty_exceptions_enable=False)

    @guarded.callback()
    def _root() -> None:
        """Root."""

    @guarded.command()
    def boom(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
        raise exc

    @guarded.command()
    def fine() -> None:
        typer.echo("fine")

    return guarded


def _run(exc: BaseException, *args: str):
    return runner.invoke(_guarded(exc), ["boom", *args])


def test_crash_is_one_line_with_class_name_and_exit_1() -> None:
    result = _run(RuntimeError(CANARY))
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert CANARY not in result.output
    assert "RuntimeError" in result.output
    assert "internal error" in result.output
    assert "--verbose" in result.output


def test_verbose_shows_traceback_and_row_data_note() -> None:
    result = _run(RuntimeError(CANARY), "--verbose")
    assert result.exit_code == 1
    assert "Traceback" in result.output
    assert "may contain row data" in result.output


def test_decoy_debug_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECOY_DEBUG", "1")
    result = _run(RuntimeError(CANARY))
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == CANARY


def test_safe_exit_carries_no_original_exception() -> None:
    group = typer.main.get_command(_guarded(RuntimeError(CANARY)))
    with pytest.raises(typer.Exit) as caught:
        with group.make_context("decoy", ["boom"]) as ctx:
            group.invoke(ctx)
    assert caught.value.exit_code == 1
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (typer.Exit(4), 4),
        (typer.Abort(), 1),
        (typer.BadParameter("x"), 2),
        (KeyboardInterrupt(), 130),
        (SystemExit(7), 7),
    ],
    ids=["exit-4", "abort", "bad-parameter", "keyboard-interrupt", "system-exit-7"],
)
def test_control_flow_exits_pass_through(exc: BaseException, code: int) -> None:
    result = _run(exc)
    assert result.exit_code == code
    assert "internal error" not in result.output


@pytest.mark.parametrize(
    "exc",
    [OSError(errno.ENOSPC, "x"), FileNotFoundError("gone")],
    ids=["enospc", "file-not-found"],
)
def test_non_epipe_oserror_is_a_crash_exit_1(exc: OSError) -> None:
    result = _run(exc)
    assert result.exit_code == 1
    assert "internal error" in result.output
    assert "Traceback" not in result.output


def test_broken_pipe_is_not_reported_as_internal_error() -> None:
    result = _run(BrokenPipeError(errno.EPIPE, "pipe"))
    assert result.exit_code == 1
    assert "internal error" not in result.output


def test_eof_error_is_aborted() -> None:
    result = _run(EOFError())
    assert result.exit_code == 1
    assert "Aborted" in result.output
    assert "internal error" not in result.output


def test_real_app_usage_errors_exit_2() -> None:
    bad_flag = runner.invoke(app, ["--no-update-check", "run", "--no-such-flag"])
    assert bad_flag.exit_code == 2
    bad_cmd = runner.invoke(app, ["--no-update-check", "no-such-command"])
    assert bad_cmd.exit_code == 2
    assert "No such command" in bad_cmd.output


def test_real_app_is_guarded() -> None:
    assert isinstance(typer.main.get_command(app), _GuardedGroup)
    assert app.pretty_exceptions_enable is False
    assert typer.BadParameter.__base__ is _USAGE_ERROR


_CRASH_SCRIPT = """
import decoy.cli.info as mod

class InfoCrash(RuntimeError):
    pass

def crash():
    raise InfoCrash("boom")

mod.info = crash
from decoy.__main__ import app
app(["--no-update-check", "info"])
"""


def test_console_script_crash_is_guarded_in_a_subprocess() -> None:
    env = {k: v for k, v in os.environ.items() if k != "DECOY_DEBUG"}
    done = subprocess.run(
        [sys.executable, "-c", _CRASH_SCRIPT], capture_output=True, text=True, env=env, check=False
    )
    assert "InfoCrash" in done.stderr
    assert "Traceback" not in done.stderr
    assert done.returncode == 1


def test_conftest_enables_decoy_debug() -> None:
    assert _DEBUG_AT_COLLECTION == "1"
