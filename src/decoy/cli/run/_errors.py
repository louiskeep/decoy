"""The catch-all error arm of `decoy run`: exception to exit code, text and output."""

from datetime import datetime, timezone
from typing import Any, NoReturn

import typer

from decoy import _mask_secret_guidance, _native_gate, _resources
from decoy._atomic import AtomicWriteError, describe
from decoy.cli import gen
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_USAGE, run_exit_code
from decoy.cli.extras import (
    MissingExtraError,
    UnsupportedCloudEndpointError,
    translate_missing_extra,
    translate_ner_unavailable,
)
from decoy.cli.gate import PreRunCheckError, cap_error_text, capacity_codes
from decoy.cli.io import OUTPUT_DIR_UNUSABLE, DuckDBSourceError, LayoutError, TargetFormatError
from decoy.cli.run._context import RunContext
from decoy.cli.run._execute import (
    _ChunkedFixedWidthError,
    _ChunkedGenerateError,
    _ChunkedIntegrityError,
    _ChunkedQuarantineError,
    _ChunkedReportFlagError,
)
from decoy.cli.run._notify import _dispatch_run_notifications, _OtelSettingsUsageError
from decoy.cli.run._prepare import _MaskSecretUsageError
from decoy.cli.run._vault import (
    VAULT_COMMIT_FAILED_HINT,
    _ChunkedVaultError,
    _VaultUsageError,
    _VaultWriteError,
)
from decoy.ui.output import OutputMode, emit_json, print_traceback
from decoy.ui.theme import error, hint

# The engine's capacity-refusal codes come from its registry (`capacity_codes()`); see
# docs/plans/2026-07-24-oom-checker-cli-v1.md R8 for why the match is narrow.

# The engine's code for a `unique` generate column or pair that the data cannot satisfy.
UNIQUENESS_IMPOSSIBLE_CODE = "uniqueness_impossible"

_OUT_OF_MEMORY_TEXT = "the run ran out of memory."


class OutDirUsageError(LayoutError):
    """`--out-dir` names something that cannot be a run's output directory.

    Always the registry's fixed `layout.output_dir_unusable` text: the caller's wording and
    the path are dropped, so nothing about the directory reaches the message.
    """

    def __init__(self, _detail: str = "") -> None:
        super().__init__(OUTPUT_DIR_UNUSABLE.code, OUTPUT_DIR_UNUSABLE.message())


def _usage_types() -> tuple[type, ...]:
    """The exception types that exit 1: the operator's request or environment is wrong.

    One tuple, read by the category rule and by `_cli_refusal_types`, so the exit and the
    reason attach rule cannot drift apart.
    """
    from decoy_engine import ConfigError, PipelineValidationError
    from decoy_engine.plan import PlanCompileError

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


def _engine_family(exc_type: type) -> bool:
    """Whether the engine's reason adapter trusts this exception class."""
    from decoy_engine.reason_adapter import registered_families

    return issubclass(exc_type, tuple(registered_families()))


def _cli_refusal_types() -> tuple[type, ...]:
    """Refusals the CLI raises itself, so the engine has no reason for them.

    The exit-1 types that are not engine families, plus the vault write failure (exit 3) and
    the gate refusal (exit 1 or 5).
    """
    owned = tuple(t for t in _usage_types() if not _engine_family(t))
    return (*owned, _VaultWriteError, PreRunCheckError)


def _failure_reason(exc: Exception, engine_exc: Exception) -> dict | None:
    """The engine's reason payload for the failure, or None when the CLI owns the refusal.

    `engine_exc` is the exception as the engine raised it, before the missing-extra and NER
    rewrites, so a rewrite keeps the engine's record. The answer is computed here only; any
    error in it drops the reason and never changes the exit.
    """
    try:
        from decoy_engine import reason_adapter

        if not _engine_family(type(engine_exc)) and isinstance(exc, _cli_refusal_types()):
            return None
        return reason_adapter.reason_from_exception(engine_exc).to_payload()
    except Exception:
        return None


def fail(ctx: RunContext, exc: Exception) -> NoReturn:
    """Map `exc` to an exit code, notify, print the error and exit. Called inside the
    `except` block so the exit keeps the exception as its context."""
    # The reason comes from the exception as raised, before the rewrites below.
    engine_exc = exc
    # Dispatch on type: config wrong (EXIT_USAGE) vs run blew up (EXIT_RUNTIME).
    # Imported lazily to keep the engine import off the help path.
    from decoy_engine import DecoyError, GenerationError, VaultError, reasons
    from decoy_engine.verification.postmask import PostScanBlockedError

    # CLI install DX (2026-09-25): a pipeline step that lazily imports an
    # optional dependency (boto3/google-cloud-storage for a cloud
    # source/target, spacy for NER, etc.) raises ImportError when the
    # matching decoy-cli extra isn't installed. Translate that into the
    # exact install line instead of a raw traceback. An ImportError for
    # anything NOT a known optional extra is left as-is (stays classified
    # EXIT_RUNTIME below -- that is a real defect, not a missing extra).
    if isinstance(exc, ImportError):
        _missing_extra = translate_missing_extra(exc)
        if _missing_extra is not None:
            exc = _missing_extra

    # CLI install DX (2026-09-25): the engine's own NerUnavailableError
    # (text_mask/text_redact `ner`) already fails closed for a missing
    # spaCy install; rewrite it to point at decoy-cli's own `[ner]`
    # extra instead of `decoy-engine[ner]` (see translate_ner_unavailable
    # docstring for why only the "spaCy absent" case is rewritten).
    _translated_ner = translate_ner_unavailable(exc)
    if _translated_ner is not None:
        exc = _translated_ner

    # DE-02: MaskSecretError lives in the engine's `keyprovider` module,
    # which a pre-DE-02 engine lacks. Import defensively so a missing
    # module never crashes the error handler itself (it would mask the
    # real exception). `()` makes the isinstance check below a harmless
    # no-op when the class is unavailable.
    try:
        from decoy_engine.keyprovider import MaskSecretError as _MaskSecretError

        _mask_secret_error_types: tuple = (_MaskSecretError,)
    except ImportError:
        _mask_secret_error_types = ()

    # OOM checker v1 (Part A): ExecutionError's two capacity-refusal codes
    # get their own exit code and JSON error_kind, distinct from a generic
    # engine crash. Same defensive-import posture as MaskSecretError above
    # -- an engine too old to have ExecutionError at all just never
    # matches, so this never crashes the error handler itself.
    try:
        from decoy_engine.execution import ExecutionError as _ExecutionError

        _execution_error_types: tuple = (_ExecutionError,)
    except ImportError:
        _execution_error_types = ()

    capacity_code: str | None = None
    if isinstance(exc, _execution_error_types) and exc.code in capacity_codes():
        capacity_code = exc.code
    # A generate run whose output cannot fit the memory
    # budget raises `GenerationBudgetExceeded`, a plain DecoyError carrying its code. It
    # is a memory refusal like the two above, so it exits 5 and labels the JSON the same.
    elif isinstance(exc, DecoyError) and getattr(exc, "code", None) in capacity_codes():
        capacity_code = exc.code
    # A bare MemoryError has no code and often no text; it is still the host running out of
    # memory, so it takes the capacity exit with fixed text instead of an empty `error: `.
    out_of_memory = isinstance(exc, MemoryError)

    # Phase 3.1: `NativeGateError.code` distinguishes a usage refusal
    # (--native/--no-native conflict, an ineligible shape) from a
    # companion-health refusal (`native_require_<reason>` /
    # `native_companion_<reason>`) -- put it in the JSON envelope so a
    # script can branch on it without parsing `error` text.
    native_code: str | None = None
    if isinstance(exc, _native_gate.NativeGateError):
        native_code = exc.code

    # The category names the failure; the exit integer comes from `RUN_EXIT_MAP`.
    if isinstance(exc, PreRunCheckError):
        if exc.exit_code == EXIT_CAPACITY:
            _category = "capacity"
        elif exc.exit_code == EXIT_USAGE:
            _category = "usage"
        else:
            raise RuntimeError("pre-run check carried an exit code with no category")
    elif capacity_code is not None or out_of_memory:
        _category = "capacity"
    elif isinstance(exc, VaultError) and exc.code == reasons.runtime.VAULT_EXISTS:
        # An existing vault is refused, never overwritten: the operator picks a new path.
        _category = "usage"
    elif isinstance(exc, PostScanBlockedError):
        # The post-scan gate withheld the output on a verdict about the data, the same
        # state as a blocking post-validation failure (exit 4), not a crash (exit 3).
        _category = None
    elif isinstance(exc, GenerationError) and exc.code == UNIQUENESS_IMPOSSIBLE_CODE:
        # A `unique` column or pair the data cannot satisfy (a parent with too
        # few distinct keys, a faker type that ran out) is fixed in the config, so it exits 1
        # like the validate-time domain checks. Other GenerationError codes (dtype_unsafe,
        # timezone_naive_datetime) stay runtime errors. The engine text is value-free.
        _category = "usage"
    else:
        _category = "usage" if isinstance(exc, _usage_types()) else "runtime"
    # CLI QA fix (2026-06-02, F8): cap the error message at 500
    # chars before emitting through --json. Engine exceptions can
    # quote source-row content verbatim (pandas / pyarrow); without
    # the truncation a single malformed row's value can land in
    # downstream log aggregators.
    error_text = describe(exc) if isinstance(exc, AtomicWriteError) else str(exc)
    if isinstance(exc, LayoutError):
        error_text = f"{exc.code}: {exc.message}"
    error_text = cap_error_text(error_text)
    if out_of_memory:
        error_text = _OUT_OF_MEMORY_TEXT
    keyed_refusal = _mask_secret_guidance.is_keyed_secret_refusal(exc)
    if isinstance(exc, _mask_secret_error_types):
        # Constant text by code; the engine message never reaches the terminal or --json.
        error_text = _mask_secret_guidance.secret_error_text(exc, _mask_secret_guidance.RUN)

    # PII egress guard (dennis sprint-5 BLOCKER): the raw engine error
    # can quote source-row cell values verbatim (see the comment above),
    # so it MUST NOT ride into an outbound notification, which is POSTed
    # to a third-party webhook / Slack / email. Only the exception TYPE
    # name goes on the wire; the raw error_text stays on local stdout /
    # stderr and the --json envelope below where the operator already
    # sees it. Redaction by construction, mirroring the platform's
    # facts-only alert rule (dispatcher.py:137-142).
    ctx.notify_results = _dispatch_run_notifications(
        ctx.notify_channels,
        notify_on=ctx.notify_on.value,
        status="failure",
        config_path=ctx.config_str,
        row_count=None,
        started_at=ctx._run_started_at,
        finished_at=datetime.now(timezone.utc),
        error_summary=type(exc).__name__,
        state=ctx.state,
    )

    # A preview shrinks the tables; a bound it can no longer meet is fixed by a larger --rows.
    raise_rows_hint = (
        ctx.rows is not None
        and isinstance(exc, GenerationError)
        and exc.code == UNIQUENESS_IMPOSSIBLE_CODE
    )

    remove_vault_hint = (
        isinstance(engine_exc, VaultError)
        and engine_exc.code == reasons.runtime.VAULT_COMMIT_FAILED
    )

    if ctx.state.mode is OutputMode.json:
        # R7: the capacity branch ADDS error_kind/code to this SAME
        # envelope -- command/config/mode/error are never dropped, and
        # this is the one emit_json call site for a run-time failure
        # (no parallel emit that would lose the 500-char cap, the
        # notify dispatch above, or quiet/verbose handling below).
        payload: dict[str, Any] = {
            "command": "run",
            "status": "error",
            "config": ctx.config_str,
            "mode": ctx.yaml_mode,
            "error": error_text,
        }
        # Only what the publication ledger holds: files a writer finished, and their folder.
        if ctx.layout is not None:
            ctx.layout.abandon()
        payload.update(ctx.published_members())
        if raise_rows_hint:
            payload["hint"] = gen.RAISE_ROWS_HINT
        if remove_vault_hint:
            payload["hint"] = VAULT_COMMIT_FAILED_HINT
        if isinstance(exc, PreRunCheckError):
            payload.update(exc.json_members())
        elif capacity_code is not None or out_of_memory:
            payload["error_kind"] = "capacity"
            if capacity_code is not None:
                payload["code"] = capacity_code
        elif native_code is not None:
            payload["error_kind"] = "native"
            payload["code"] = native_code
        elif isinstance(exc, MissingExtraError):
            # A machine-detectable field, not just the
            # `[missing_extra]`-prefixed message text.
            payload["error_kind"] = "missing_extra"
            payload["extra"] = exc.extra
        reason = _failure_reason(exc, engine_exc)
        if reason is not None:
            payload["reason"] = reason
        if ctx.notify_channels:
            payload["notify"] = ctx.notify_results
        emit_json(ctx.state, payload)
    elif ctx.state.mode is not OutputMode.quiet:
        # CLI install DX (2026-09-25): error_text is arbitrary exception
        # text, not authored UI copy -- it can legitimately contain `[`
        # (a MissingExtraError's `pip install decoy-cli[cloud]`, a
        # Phase 3.1 native-gate message quoting `decoy-cli[native]` or a
        # companion's own ABI string, or any future message that quotes
        # a list/bracketed value). markup=False so Rich prints it
        # verbatim instead of parsing it as markup and silently
        # dropping an unrecognized tag.
        if isinstance(exc, PreRunCheckError):
            # The summary already names the command that lists every finding.
            label = "capacity:" if exc.error_kind == "capacity" else "error:"
            ctx.state.err_console.print(error(label), error_text, markup=False)
        elif capacity_code is not None or out_of_memory:
            ctx.state.err_console.print(error("capacity:"), error_text, markup=False)
            ctx.state.err_console.print(
                " ",
                hint("hint:"),
                "this job needs more memory than this host has; use a larger "
                "tier or reduce the job.",
            )
        elif keyed_refusal:
            ctx.state.err_console.print(error("error:"), error_text, markup=False)
        else:
            ctx.state.err_console.print(error("error:"), error_text, markup=False)
            if raise_rows_hint:
                ctx.state.err_console.print(" ", hint("hint:"), gen.RAISE_ROWS_HINT)
            if remove_vault_hint:
                ctx.state.err_console.print(" ", hint("hint:"), VAULT_COMMIT_FAILED_HINT)
            ctx.state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback."
            )
    if ctx.state.verbose:
        print_traceback(ctx.state)
    raise typer.Exit(
        code=run_exit_code(_category, blocking_failed=isinstance(exc, PostScanBlockedError))
    )
