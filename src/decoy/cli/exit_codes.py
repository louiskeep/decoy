"""Named exit-code constants for the `decoy` CLI surface (OSS.1 / OSS-CODE-4).

The CLI commits to a stable, documented set of process exit codes; before this
module those codes lived as integer literals scattered across nine CLI modules
(`raise typer.Exit(code=1)`, `code=3`, etc.), a public contract held together
only by convention. A single typo would silently change the contract; a
contributor reading the source had no way to learn what each code meant short
of grepping every call site.

The values below are the public exit-code contract. Their INTEGER VALUES
are stable across releases (callers in shell scripts, CI pipelines, and Make
recipes depend on them). The names may evolve; the integers may not. Code 2 is
EXIT_WARNINGS: a command ran clean except for advisory warnings and
`--fail-on-warning` was set (the warning-blocking CI gate). Previously the
integer belonged to the `forge` deprecation shim (removed pre-GA) and S1 docs
mislabeled it "reserved/unused"; in fact `validate`/`preflight` already
returned 2 under `--fail-on-warning`, so S2 promotes it to this public name.
The integer 2 is also what Click exits on a usage error; `decoy run` maps its parameter
failures to that same integer, not the same meaning (see the `RUN_EXIT_MAP` comment).

OSS.4b (2026-06-02) added EXIT_FINDINGS=4 to support `decoy report integrity`
(which began under the now-retired `storm` group, relocated in S4b), which has
a meaningful 4th state distinct from the existing three: the
operation ran cleanly, but the data being checked has issues the integrity
runner flagged. Adding a new constant is a MINOR-eligible additive change per
docs/release/versioning.md (existing integers 0-3 do not move). Source
pattern: semgrep's exit-code split (0 pass, 1 findings, 2 error); the analog
here is 0 clean / 4 findings / 3 runtime crash.

The OOM checker v1 (2026-07-24) added EXIT_CAPACITY=5: `decoy run` and
`decoy validate preflight` both need a way to say "this job needs more memory
than the host has" distinctly from a generic engine crash (EXIT_RUNTIME) or a
bad config (EXIT_USAGE). The value is `5` -- 0, 1, 2, 3, and 4 are pinned and
do not move (2 is EXIT_WARNINGS, see above).

Reference: README "Exit codes" section + `decoy explain exit-codes`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, cast

EXIT_OK: int = 0
"""Command succeeded. The default exit code for a clean run; matches POSIX
convention. `typer.Exit()` with no argument also exits 0."""

EXIT_USAGE: int = 1
"""Command failed because the user gave bad input: a config that did not pass
validation, a path that did not exist, a flag combination that was invalid.
The fix is in the user's request, not in the CLI itself."""

EXIT_WARNINGS: int = 2
"""The command ran clean except for advisory warnings, and `--fail-on-warning`
was set. Returned by `decoy validate config`/`validate preflight` (and the
`validate` aggregate) when no error or failure fired but at least one warning
did and the caller opted to treat warnings as blocking. Without
`--fail-on-warning` the same run exits EXIT_OK. (The integer previously
belonged to the removed `forge` deprecation shim; it is reused here rather
than held open, since a warning-blocking result is a genuinely distinct state
from EXIT_OK and EXIT_USAGE.)"""

EXIT_RUNTIME: int = 3
"""The CLI itself blew up at run time: the engine raised an unexpected error,
an output write failed, a temp file vanished mid-run. The fix is in the CLI
or engine, not in the user's request. Distinct from EXIT_USAGE so CI
pipelines can route a runtime crash to a different alert."""

EXIT_FINDINGS: int = 4
"""The CLI ran cleanly but found data issues. Used by data-validation /
integrity verbs (`decoy report integrity` is the first; future verbs that
audit data rather than execute it will reuse this code). The fix is in the
data being checked, not in the CLI or the user's invocation. Pattern source:
semgrep's exit-code split (0 pass, 1 findings, 2 error). Distinct from
EXIT_USAGE (the user gave bad input) and EXIT_RUNTIME (the CLI crashed)."""

EXIT_CAPACITY: int = 5
"""The job needs more memory than this host (or the budget it was given) has.
Raised by `decoy run` when the engine refuses a job for memory, and by
`decoy validate preflight` when its capacity check predicts the same refusal before
the run starts. The fix is a bigger host/cgroup ceiling or a smaller job -- not a
config mistake (EXIT_USAGE) and not an engine defect (EXIT_RUNTIME).

Which refusals count is the engine's call: `decoy_engine.errors.CAPACITY_REASON_CODES`
(read through `decoy.cli.gate.capacity_codes()`), so the CLI keeps no list of its own.
Today that set holds `out_of_core_fanin_exceeds_budget`, `out_of_core_insufficient_memory`,
`out_of_core_faker_pool_budget_exceeded`, `out_of_core_reorder_budget_too_small`,
`pool_exceeds_cache_budget`, `generation_budget_exceeded`, `process_out_of_memory` and
`isolated_worker_out_of_memory`; a bare `MemoryError` also exits 5. The engine lists every
other budget or capacity code with the reason it is not capacity (a rejected setting, disk or
quota, a routing refusal, a different limit) and those keep their usual exit.

The build-floor estimate of the out-of-core-FK gate is advisory: a job over it warns and
does not exit 5. `out_of_core_insufficient_memory` stays in the set for engines that still
raise it. `decoy validate preflight` checks the out-of-core-FK route and the generation
budget; see `decoy explain exit-codes`."""

EXIT_PARTIAL: int = 6
"""The run delivered some of its tables and withheld the rest (best-effort delivery).
Reserved: no path reaches it until best-effort delivery ships. Distinct from EXIT_RUNTIME so a
script can tell a partial delivery from a crash. Ranks between EXIT_USAGE and EXIT_FINDINGS in
`decoy ci` precedence."""

# Status Typer returns for Ctrl-C (128 plus SIGINT). Private: a public `EXIT_` name in `__all__`
# would join the `decoy ci` taxonomy, and 130 must not.
_EXIT_INTERRUPTED = 130

# Where `decoy run` turns an outcome into an exit integer. The error handler and the
# `--post-validate-enforce` exits read it now; the remaining early refusals move to it later. The
# key is the engine's `(status, failure category)`. Read-only; a test patches the module name.
# `(failed, parameter)` is 2 because Click exits 2 on a usage error; the value is the same
# integer as EXIT_WARNINGS, not the same meaning. Ctrl-C is 130, the status Typer returns today.
RUN_EXIT_MAP: Mapping[tuple[str, str | None], int] = MappingProxyType(
    {
        ("succeeded", None): EXIT_OK,
        ("findings", None): EXIT_FINDINGS,
        ("partially_delivered", None): EXIT_PARTIAL,
        ("failed", "usage"): EXIT_USAGE,
        ("failed", "parameter"): EXIT_WARNINGS,
        ("failed", "runtime"): EXIT_RUNTIME,
        ("failed", "capacity"): EXIT_CAPACITY,
        ("cancelled", "cancelled"): _EXIT_INTERRUPTED,
    }
)


def run_exit_code(category: str | None = None, *, blocking_failed: bool = False) -> int:
    """The exit integer of a `decoy run` outcome, read through the engine's `derive_outcome`."""
    # Imported here so the engine stays off the `--help` path.
    from decoy_engine.run_result import derive_outcome

    return derive_outcome(
        category=cast(Any, category),
        delivery_mode="in_place",
        delivery_outcome="nothing",
        blocking_failed=blocking_failed,
        exit_map=RUN_EXIT_MAP,
    ).exit_code


__all__ = [
    "EXIT_CAPACITY",
    "EXIT_FINDINGS",
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_RUNTIME",
    "EXIT_USAGE",
    "EXIT_WARNINGS",
    "RUN_EXIT_MAP",
]
