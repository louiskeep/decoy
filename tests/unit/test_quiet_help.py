"""Every `--quiet` option says errors still reach stderr, so no one expects silence on failure."""

from __future__ import annotations

import re

from tests.command_tree import options

STATES_ERRORS = re.compile(r"errors? still (go to|print)", re.IGNORECASE)


def _quiet_options() -> list[tuple[str, str]]:
    return [
        (" ".join(o.cmd.path), getattr(o.param, "help", None) or "")
        for o in options()
        if o.cmd.path and "--quiet" in o.spellings
    ]


def test_every_quiet_option_says_errors_still_print() -> None:
    options = _quiet_options()
    assert len(options) >= 30
    missing = [name for name, help_ in options if not STATES_ERRORS.search(help_)]
    assert missing == []
