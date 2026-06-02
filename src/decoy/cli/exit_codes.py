"""Named exit-code constants for the `decoy` CLI surface (OSS.1 / OSS-CODE-4).

The CLI commits to a stable, documented set of process exit codes; before this
module those codes lived as integer literals scattered across nine CLI modules
(`raise typer.Exit(code=1)`, `code=3`, etc.), a public contract held together
only by convention. A single typo would silently change the contract; a
contributor reading the source had no way to learn what each code meant short
of grepping every call site.

The four values below are the public exit-code contract. Their INTEGER VALUES
are stable across releases (callers in shell scripts, CI pipelines, and Make
recipes depend on them). The names may evolve; the integers may not.

Reference: README "Exit codes" section + `decoy explain exit-codes`.
"""

from __future__ import annotations

EXIT_OK: int = 0
"""Command succeeded. The default exit code for a clean run; matches POSIX
convention. `typer.Exit()` with no argument also exits 0."""

EXIT_USAGE: int = 1
"""Command failed because the user gave bad input: a config that did not pass
validation, a path that did not exist, a flag combination that was invalid.
The fix is in the user's request, not in the CLI itself."""

EXIT_DEPRECATED_SHIM: int = 2
"""The legacy `forge` console script was invoked. The user is on the old name;
the CLI prints a migration hint and exits without running. Reserved for the
`decoy._deprecated` shim only; do not reuse for other deprecation cases
without a public-contract conversation first."""

EXIT_RUNTIME: int = 3
"""The CLI itself blew up at run time: the engine raised an unexpected error,
an output write failed, a temp file vanished mid-run. The fix is in the CLI
or engine, not in the user's request. Distinct from EXIT_USAGE so CI
pipelines can route a runtime crash to a different alert."""

__all__ = [
    "EXIT_OK",
    "EXIT_USAGE",
    "EXIT_DEPRECATED_SHIM",
    "EXIT_RUNTIME",
]
