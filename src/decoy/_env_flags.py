"""The CLI's one reader for environment switches.

One accepted set, compared after `strip().lower()`: true is `1`, `true`, `yes`, `on`; false is
`0`, `false`, `no`, `off`. An unset or empty variable gives the switch's default. The engine
uses the same set, so one spelling means the same thing on both sides of the boundary.

Every CLI switch fails safe and never exits. These readers run at startup and inside the
global crash handler, where raising would hide the error the user came to see. So there is no
refusing parser here: each caller names the side an unknown spelling takes, and that side is
the one that leaks or costs least (debug tracebacks off, the update check off).

`env_int` is the one place that refuses: a number the user mistyped is a setting error to
report, not a switch to guess. Its message names the variable and never the value.

This module imports nothing from `decoy`, so any tier may use it.
"""

from __future__ import annotations

import os

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _spelling(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def safe_env_flag(name: str, *, default: bool, unknown: bool) -> bool:
    """The flag's value: `default` when unset or empty, `unknown` for an unrecognised spelling."""
    value = _spelling(name)
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return unknown


def is_ci() -> bool:
    """True when `CI` is set to anything but empty or a false spelling (the CI convention)."""
    value = _spelling("CI")
    return bool(value) and value not in _FALSE


def no_color() -> bool:
    """True for any non-empty `NO_COLOR`, as no-color.org specifies; empty keeps colour."""
    return bool(os.environ.get("NO_COLOR"))


def env_int(name: str, default: int) -> int:
    """The variable as an int, `default` when unset or empty; a non-integer is a `ValueError`."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        pass
    # Raised outside the handler so the error carries no `__context__`: the parser's text
    # quotes the rejected value.
    raise ValueError(f"{name} must be a whole number.")
