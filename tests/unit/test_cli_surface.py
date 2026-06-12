"""CLI surface drift sentry.

`docs/cli-reference.md` is generated from the Typer app with:

    python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md

This guard re-renders the reference from the current command tree and asserts it
equals the committed file. If a command or flag is added, renamed, or removed
without the reference being regenerated, this fails.

That is the point: the command/flag surface cannot change without its docs being
refreshed. To fix a failure, regenerate and commit:

    python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "docs" / "cli-reference.md"


def _render() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "typer", "decoy.__main__", "utils", "docs", "--name", "decoy"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"typer utils docs failed:\n{proc.stderr}"
    return proc.stdout


def test_cli_reference_is_up_to_date():
    assert REFERENCE.exists(), (
        f"{REFERENCE} is missing. Regenerate it:\n"
        "  python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md"
    )
    # Normalize trailing whitespace/newlines (stdout vs --output differ only there).
    expected = _render().rstrip()
    actual = REFERENCE.read_text(encoding="utf-8").rstrip()
    assert actual == expected, (
        "docs/cli-reference.md is stale: the CLI command/flag surface changed but "
        "the reference was not regenerated. Run:\n"
        "  python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md\n"
        "and commit the result. (A command/flag change must update its docs.)"
    )
