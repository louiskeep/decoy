"""Shared pytest configuration for the decoy CLI test suite.

Force plain (non-ANSI) CLI output for the whole test session. Several e2e tests
assert plain option/help substrings (e.g. ``"--explain" in result.stdout``).
Rich emits ANSI color under a color-capable or CI terminal (``FORCE_COLOR``),
which interleaves escape codes into those strings and breaks the substring
match, so the tests pass locally (no color) but fail in CI (color). Neutralizing
color here makes the assertions terminal-agnostic (local == CI).

Set at import time, before pytest collects any test and before any Typer/Rich
Console is constructed: ``NO_COLOR`` alone does not win against ``FORCE_COLOR``
in Rich, so drop ``FORCE_COLOR`` and mark the terminal dumb as well.
"""

import os

os.environ.pop("FORCE_COLOR", None)
os.environ["NO_COLOR"] = "1"
os.environ["TERM"] = "dumb"
