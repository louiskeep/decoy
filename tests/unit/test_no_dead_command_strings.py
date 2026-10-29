"""Grep gate: no source string under `src/decoy/` names a deleted command.

S2 re-parented `compile`/`preflight` under `validate` and folded
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
    # S2: top-level commands removed / re-parented. The space is load-bearing:
    # it keeps `decoy validate preflight` and `decoy validate compile` (the
    # live forms) from matching `decoy preflight` / `decoy compile`.
    "decoy compile",
    "decoy plan",
    "decoy preflight",
    # S3a: `profile` merged into the Pre-scan verb. The Pre-scan / Post-scan
    # rename's dead spellings are enforced by the residual sentry
    # (tests/sentry/test_no_residual_removed_surface.py).
    "decoy profile",
    # S3b: the `strategies`/`providers`/`checksums`/`validators` sub-apps and the
    # `templates` sub-app folded into `decoy list KIND` / `decoy show KIND`. The
    # removed top-level invocation strings are dead. `decoy templates` catches
    # both `templates list` and `templates show`; it does NOT match the live
    # `decoy list templates` / `decoy show template` forms (no "decoy templates"
    # substring in either).
    "decoy strategies",
    "decoy providers",
    "decoy checksums",
    "decoy validators",
    "decoy templates",
    # S4a: the project/catalog/jobs persistence subsystem was deleted and the
    # CLI is now stateless. The trailing space keeps `decoy report ...` (the
    # live post-run surface) from matching; none of these three has a
    # surviving `decoy ...` form.
    "decoy project",
    "decoy catalog",
    "decoy jobs",
    # S4b: the `evidence` and `vault` groups and `validate distribution` folded
    # into `decoy report` (verify+show / vault). `validate distribution` (the
    # exact nested path) is dead; `decoy evidence` / `decoy vault` catch every
    # invocation of those removed groups.
    "decoy evidence",
    "decoy vault",
    "validate distribution",
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
