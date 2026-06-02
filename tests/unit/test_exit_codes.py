"""Pin the public exit-code contract (OSS.1 / OSS-CODE-4 / G7).

Two cells:

  1. ``test_named_constants_have_pinned_integer_values`` -- the integer
     values are the public API. Scripts and CI pipelines depend on them.
     Names may evolve; integers may not.
  2. ``test_no_remaining_literal_typer_exits_in_cli_source`` -- drift
     guard. After OSS.1 the CLI source carries zero ``typer.Exit(code=N)``
     digit literals; every exit goes through one of the four named
     constants. A future contributor who adds ``typer.Exit(code=5)``
     trips this test.

Reference: README "Exit codes" section, ``decoy explain exit-codes``.
"""

from __future__ import annotations

import re
from pathlib import Path

from decoy.cli import exit_codes


def test_named_constants_have_pinned_integer_values() -> None:
    """Pin the integer-value contract: 0/1/2/3 are stable across releases."""
    assert exit_codes.EXIT_OK == 0
    assert exit_codes.EXIT_USAGE == 1
    assert exit_codes.EXIT_DEPRECATED_SHIM == 2
    assert exit_codes.EXIT_RUNTIME == 3
    # __all__ covers exactly the four public names; any rename of an
    # existing constant or addition of a new public symbol must update
    # __all__ deliberately rather than slip through.
    assert set(exit_codes.__all__) == {
        "EXIT_OK",
        "EXIT_USAGE",
        "EXIT_DEPRECATED_SHIM",
        "EXIT_RUNTIME",
    }


def test_no_remaining_literal_typer_exits_in_cli_source() -> None:
    """Drift guard: every ``raise typer.Exit(code=...)`` site in the CLI
    must reference a named constant, not a digit literal. Catches the
    case where a future contributor adds ``typer.Exit(code=5)`` and
    silently extends the public contract.

    Scope: ``src/decoy/cli/`` plus the closely-coupled ``src/decoy/ui/``
    + ``src/decoy/_deprecated.py``. The exit_codes module itself is
    excluded (its docstring intentionally cites the legacy pattern as
    an example of what is being centralized)."""
    cli_root = Path(__file__).resolve().parent.parent.parent / "src" / "decoy"
    pattern = re.compile(r"typer\.Exit\(code=\d|sys\.exit\(\d")
    offenders: list[tuple[Path, int, str]] = []
    skip_names = {"exit_codes.py"}
    for path in cli_root.rglob("*.py"):
        if path.name in skip_names:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append((path, lineno, line.strip()))
    assert not offenders, (
        "Found digit-literal exit codes that bypass exit_codes.py. "
        "Replace with the appropriate EXIT_* constant:\n  "
        + "\n  ".join(f"{p.name}:{ln}: {src}" for p, ln, src in offenders)
    )
