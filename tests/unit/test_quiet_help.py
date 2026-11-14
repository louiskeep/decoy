"""Every `--quiet` option says errors still reach stderr, so no one expects silence on failure."""

from __future__ import annotations

import re

import typer.main

from decoy.__main__ import app

STATES_ERRORS = re.compile(r"errors? still (go to|print)", re.IGNORECASE)


def _quiet_options() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def visit(cmd: object, prefix: tuple[str, ...]) -> None:
        for name, sub in getattr(cmd, "commands", {}).items():
            path = (*prefix, name)
            for param in getattr(sub, "params", []):
                if "--quiet" in getattr(param, "opts", []):
                    found.append((" ".join(path), getattr(param, "help", None) or ""))
            visit(sub, path)

    visit(typer.main.get_command(app), ())
    return found


def test_every_quiet_option_says_errors_still_print() -> None:
    options = _quiet_options()
    assert len(options) >= 30
    missing = [name for name, help_ in options if not STATES_ERRORS.search(help_)]
    assert missing == []
