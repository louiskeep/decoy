"""The CLI's one environment-flag rule, and the sites that read it.

Every flag the CLI reads fails safe: an unknown spelling picks a documented side and never
exits, because the readers run at startup and inside the global crash handler.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from decoy import _env_flags, _update_check
from decoy.__main__ import _GuardedGroup, app
from decoy.ui.output import _make_console

TRUE_SPELLINGS = ["1", "true", "yes", "on", " TRUE ", "Yes", "ON"]
FALSE_SPELLINGS = ["0", "false", "no", "off", " False ", "NO", "Off"]
UNKNOWN_SPELLINGS = ["maybe", "y", "t", "n", "f", "2", "enabled"]


@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize("unknown", [True, False])
def test_unset_and_empty_give_the_default(
    monkeypatch: pytest.MonkeyPatch, default: bool, unknown: bool
) -> None:
    monkeypatch.delenv("DECOY_T_FLAG", raising=False)
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=default, unknown=unknown) is default
    monkeypatch.setenv("DECOY_T_FLAG", "")
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=default, unknown=unknown) is default


@pytest.mark.parametrize("spelling", TRUE_SPELLINGS)
def test_true_spellings(monkeypatch: pytest.MonkeyPatch, spelling: str) -> None:
    monkeypatch.setenv("DECOY_T_FLAG", spelling)
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=False, unknown=False) is True


@pytest.mark.parametrize("spelling", FALSE_SPELLINGS)
def test_false_spellings(monkeypatch: pytest.MonkeyPatch, spelling: str) -> None:
    monkeypatch.setenv("DECOY_T_FLAG", spelling)
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=True, unknown=True) is False


@pytest.mark.parametrize("spelling", UNKNOWN_SPELLINGS)
@pytest.mark.parametrize("unknown", [True, False])
def test_unknown_spelling_picks_the_declared_side(
    monkeypatch: pytest.MonkeyPatch, spelling: str, unknown: bool
) -> None:
    monkeypatch.setenv("DECOY_T_FLAG", spelling)
    got = _env_flags.safe_env_flag("DECOY_T_FLAG", default=not unknown, unknown=unknown)
    assert got is unknown


def test_the_flag_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECOY_T_FLAG", "1")
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=False, unknown=False) is True
    monkeypatch.setenv("DECOY_T_FLAG", "0")
    assert _env_flags.safe_env_flag("DECOY_T_FLAG", default=False, unknown=False) is False


@pytest.mark.parametrize("value", [None, "", "false", "0", "no", "off", " FALSE "])
def test_is_ci_false(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("CI", raising=False)
    else:
        monkeypatch.setenv("CI", value)
    assert _env_flags.is_ci() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "jenkins", "maybe"])
def test_is_ci_true(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CI", value)
    assert _env_flags.is_ci() is True


@pytest.mark.parametrize(("value", "expected"), [(None, False), ("", False), ("1", True), ("x", True)])
def test_no_color_is_any_non_empty_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    if value is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", value)
    assert _env_flags.no_color() is expected


def test_env_int_reads_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECOY_T_INT", raising=False)
    assert _env_flags.env_int("DECOY_T_INT", 587) == 587
    monkeypatch.setenv("DECOY_T_INT", "")
    assert _env_flags.env_int("DECOY_T_INT", 587) == 587
    monkeypatch.setenv("DECOY_T_INT", " 25 ")
    assert _env_flags.env_int("DECOY_T_INT", 587) == 25


@pytest.mark.parametrize("bad", ["CANARY-9", "1.5", "0x10"])
def test_env_int_refuses_a_non_integer_naming_only_the_variable(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("DECOY_T_INT", bad)
    with pytest.raises(ValueError, match="DECOY_T_INT") as caught:
        _env_flags.env_int("DECOY_T_INT", 587)
    assert bad not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


# AT-CL2-1: the CI convention at the update check ---------------------------------------


class _Tty:
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(("value", "ci"), [("false", False), ("0", False), ("true", True), ("1", True)])
def test_update_check_reads_ci_through_the_one_rule(
    monkeypatch: pytest.MonkeyPatch, value: str, ci: bool
) -> None:
    monkeypatch.setattr(sys, "stderr", _Tty())
    monkeypatch.setattr(sys, "stdout", _Tty())
    monkeypatch.setenv("CI", value)
    assert _update_check._interactive() is (not ci)


# AT-CL2-2: unknown values never exit and pick the safe side -----------------------------


def _watch_the_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(_update_check, "_interactive", lambda: True)
    touched: list[str] = []

    def fetch(url: str, *args: object, **kwargs: object) -> str | None:
        touched.append(url)
        return None

    monkeypatch.setattr(_update_check, "_fetch_latest", fetch)
    return touched


def test_unknown_opt_out_means_opted_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    touched = _watch_the_network(monkeypatch, tmp_path)
    monkeypatch.setenv("DECOY_NO_UPDATE_CHECK", "maybe")
    assert _update_check.maybe_print_notice() is False
    assert touched == []


def test_zero_opt_out_still_runs_the_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    touched = _watch_the_network(monkeypatch, tmp_path)
    monkeypatch.setenv("DECOY_NO_UPDATE_CHECK", "0")
    _update_check.maybe_print_notice()
    assert len(touched) == 1


def test_command_exits_zero_with_an_unknown_opt_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import decoy.__main__ as main

    touched = _watch_the_network(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "_key_unresolved", lambda: False)
    monkeypatch.setenv("DECOY_NO_UPDATE_CHECK", "maybe")
    result = CliRunner().invoke(app, ["explain", "exit-codes"])
    assert result.exit_code == 0, result.output
    assert touched == []


def _guarded_boom() -> typer.Typer:
    guarded = typer.Typer(cls=_GuardedGroup, pretty_exceptions_enable=False)

    @guarded.callback()
    def _root() -> None:
        """Root."""

    @guarded.command()
    def boom() -> None:
        raise RuntimeError("CANARY-123")

    return guarded


def test_unknown_debug_value_leaves_debug_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECOY_DEBUG", "maybe")
    result = CliRunner().invoke(_guarded_boom(), ["boom"])
    assert result.exit_code == 1
    assert "internal error (RuntimeError)" in result.output
    assert "CANARY-123" not in result.output


@pytest.mark.parametrize("spelling", ["1", "true", "YES"])
def test_accepted_debug_spellings_reraise(monkeypatch: pytest.MonkeyPatch, spelling: str) -> None:
    monkeypatch.setenv("DECOY_DEBUG", spelling)
    result = CliRunner().invoke(_guarded_boom(), ["boom"])
    assert isinstance(result.exception, RuntimeError)


# AT-CL2-3: NO_COLOR ----------------------------------------------------------------------


def test_empty_no_color_keeps_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "")
    assert _make_console(stderr=False).no_color is False


def test_no_color_one_disables_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert _make_console(stderr=False).no_color is True
