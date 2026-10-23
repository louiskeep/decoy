"""Grep gate: no source string under `src/decoy/` names a deleted command.

The CLI-redesign S1 sprint removed the `storm scan` alias and the `storm test`
demo command. S2 re-parented `compile`/`preflight` under `validate` and folded
`plan` into `validate compile`, so the top-level invocation strings `decoy
compile`, `decoy plan`, and `decoy preflight` (note the trailing space -- the
nested `decoy validate preflight` / `decoy validate compile` forms are the live
ones and must NOT trip) are now dead too.

The CLI-surface drift sentry (`test_cli_surface.py`) covers the generated
reference, but it does NOT see hand-written help text, epilogs, docstrings, or
comments. This test closes that gap: each dead substring must appear in no
Python source file shipped under `src/decoy/`.

Tests live under `tests/`, so this file's own mention of those strings (and
any other test's) is out of scope by construction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "decoy"

DEAD_STRINGS = (
    "storm scan",
    "storm test",
    # S2: top-level commands removed / re-parented. The space is load-bearing:
    # it keeps `decoy validate preflight` and `decoy validate compile` (the
    # live forms) from matching `decoy preflight` / `decoy compile`.
    "decoy compile",
    "decoy plan",
    "decoy preflight",
    # S3a: `profile` + `storm analyze` merged into `decoy scan`; the saved-scan
    # subcommands moved from `storm` to `scan`. `storm integrity` stays live and
    # is NOT listed here.
    "decoy profile",
    "decoy storm analyze",
    "storm fields",
    "storm show",
    "storm diff",
)


@pytest.mark.parametrize("dead", DEAD_STRINGS)
def test_dead_command_string_absent_from_source(dead: str) -> None:
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if dead in line:
                offenders.append(f"{path.relative_to(SRC_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"Found {dead!r} in source (deleted command name must not be advertised):\n  "
        + "\n  ".join(offenders)
    )
