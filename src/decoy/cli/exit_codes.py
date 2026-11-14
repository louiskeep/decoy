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


def exit_code_for(exc: BaseException) -> int:
    """The exit integer a command gives `exc`: the one exception-to-exit map.

    A pure function of the exception's type and code. Categories: a pre-run gate refusal keeps
    its own 1 or 5; a capacity refusal (an engine error whose code is in the engine's capacity
    set, or a bare `MemoryError`) is 5; a config file that cannot be read as a mapping
    (`ConfigFileError`), an engine `EnvFlagError`, the usage types of `decoy run` and a
    `unique` generate column the data cannot satisfy are 1; `fit`'s differential-privacy
    errors are 3 for a provenance refusal and a budget schedule mismatch and 1 for the rest;
    a blocking post-scan finding (`PostScanBlockedError`) is 4 and an existing vault (`vault_exists`) is 1;
    Ctrl-C is 130; everything else, an `OSError` on a config read included, is 3.

    The engine and CLI exception types are imported here, not at module level: the CI modules
    and `ui.output` import this file and must not load the engine.

    Until CL4 (DUP-FREEZE) the run classifier in `cli/run/_errors.py`, `demo`'s map and `fit`'s
    arms still decide for themselves; `tests/unit/test_exit_code_for.py` holds this function
    equal to each of them.
    """
    if isinstance(exc, KeyboardInterrupt):
        return _EXIT_INTERRUPTED

    from decoy._config_file import ConfigFileError
    from decoy.cli.gate import PreRunCheckError, capacity_codes

    if isinstance(exc, PreRunCheckError):
        if exc.exit_code in (EXIT_CAPACITY, EXIT_USAGE):
            return exc.exit_code
        raise RuntimeError("pre-run check carried an exit code with no category")
    if isinstance(exc, ConfigFileError):
        return EXIT_USAGE

    from decoy_engine import DecoyError, GenerationError, VaultError
    from decoy_engine.quality.carriers import CarrierError
    from decoy_engine.quality.dp import DpError
    from decoy_engine.quality.dp_budget import DpBudgetError
    from decoy_engine.quality.dp_provenance import ProvenanceError
    from decoy_engine.reasons.quality import DP_SCHEDULE_MISMATCH
    from decoy_engine.verification.postmask import PostScanBlockedError

    if isinstance(exc, ProvenanceError):
        return EXIT_RUNTIME
    if isinstance(exc, DpBudgetError):
        return EXIT_RUNTIME if exc.code == DP_SCHEDULE_MISMATCH else EXIT_USAGE
    if isinstance(exc, (DpError, CarrierError)):
        return EXIT_USAGE

    if isinstance(exc, MemoryError):
        return EXIT_CAPACITY
    if isinstance(exc, DecoyError) and getattr(exc, "code", None) in capacity_codes():
        return EXIT_CAPACITY

    # The literal moves here when the reason-code ratchet allows a 1:1 re-home (owner decision
    # pending), so the constant stays in `cli/run/_errors.py` for now.
    from decoy.cli.run._errors import UNIQUENESS_IMPOSSIBLE_CODE

    if isinstance(exc, GenerationError) and exc.code == UNIQUENESS_IMPOSSIBLE_CODE:
        return EXIT_USAGE
    # A blocking post-scan finding is a data result, as `--post-validate-enforce` is.
    if isinstance(exc, PostScanBlockedError):
        return EXIT_FINDINGS
    # An existing vault is the caller's to resolve. The literal moves to the engine's constant
    # when the repin that ships it lands (the pinned 0.23.0 has none).
    if isinstance(exc, VaultError) and exc.code == "vault_exists":
        return EXIT_USAGE
    if isinstance(exc, usage_error_types()):
        return EXIT_USAGE
    # `EnvFlagError` ships in engine 0.24.0; the lookup is by name so 0.23.0 just has none.
    from decoy_engine import errors as engine_errors

    env_flag_error = getattr(engine_errors, "EnvFlagError", None)
    if env_flag_error is not None and isinstance(exc, env_flag_error):
        return EXIT_USAGE
    if isinstance(exc, ImportError):
        from decoy.cli.extras import translate_missing_extra

        # An import failure for a known optional extra is the missing-extra usage error.
        if translate_missing_extra(exc) is not None:
            return EXIT_USAGE
    return EXIT_RUNTIME


def usage_error_types() -> tuple[type, ...]:
    """The exception types that exit 1: the operator's request or environment is wrong.

    One tuple, read by the exit map and by the run error arm's reason-attach rule, so the two
    cannot drift apart. The imports are lazy: the run package imports this module.
    """
    from decoy_engine import ConfigError, PipelineValidationError
    from decoy_engine.plan import PlanCompileError

    from decoy import _native_gate, _resources
    from decoy.cli.extras import MissingExtraError, UnsupportedCloudEndpointError
    from decoy.cli.io import DuckDBSourceError, LayoutError, TargetFormatError
    from decoy.cli.run._errors import OutDirUsageError
    from decoy.cli.run._execute import (
        _ChunkedFixedWidthError,
        _ChunkedGenerateError,
        _ChunkedIntegrityError,
        _ChunkedQuarantineError,
        _ChunkedReportFlagError,
    )
    from decoy.cli.run._notify import _OtelSettingsUsageError
    from decoy.cli.run._prepare import _MaskSecretUsageError
    from decoy.cli.run._vault import _ChunkedVaultError, _VaultUsageError

    # Defensive imports: an engine build without the class just never matches.
    try:
        from decoy_engine.detection.ner import NerUnavailableError

        ner: tuple[type, ...] = (NerUnavailableError,)
    except ImportError:
        ner = ()
    try:
        from decoy_engine.keyprovider import MaskSecretError

        mask_secret: tuple[type, ...] = (MaskSecretError,)
    except ImportError:
        mask_secret = ()
    return (
        PlanCompileError,
        PipelineValidationError,
        ConfigError,
        _ChunkedGenerateError,
        _ChunkedFixedWidthError,
        _ChunkedIntegrityError,
        _ChunkedQuarantineError,
        TargetFormatError,
        LayoutError,
        _ChunkedReportFlagError,
        _ChunkedVaultError,
        _VaultUsageError,
        _MaskSecretUsageError,
        _OtelSettingsUsageError,
        _resources.ResourceError,
        DuckDBSourceError,
        OutDirUsageError,
        MissingExtraError,
        UnsupportedCloudEndpointError,
        *ner,
        _native_gate.NativeGateError,
        *mask_secret,
    )


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
