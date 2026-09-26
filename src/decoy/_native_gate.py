"""Shared fail-closed gate for the CLI `--native`/`--no-native` flags and the
`decoy.mask(native=...)` library argument (Phase 3.1 approach 3).

`decoy run` and `decoy.mask()` each call `run_pipeline` independently, so a
gate implemented only in `decoy/cli/run.py` would leave `decoy.mask(native=
True)` free to silently write an ineligible-shape result the CLI would
refuse. Both call sites route through the two functions here instead:

- `pre_execution_gate`: resolves the native intent (default / require /
  disable) plus the installed companion's probe status into a decision
  (what `unified_slice_enabled` to pass, and any info/warn text to show)
  BEFORE `run_pipeline` is ever called. Raises `NativeGateError` for a
  refusal that must happen before any compute (an absent/broken companion
  under `--native`, or `--native` on a shape that can never route through
  the unified slice).
- `post_run_verify`: after `run_pipeline` returns and BEFORE either write
  point (the CLI's `_write_mask_outputs` / `mask()`'s own return), asserts
  that `--native` actually got a compiled kernel to run. Raises
  `NativeGateError` otherwise, so nothing is written.

This module does no I/O (printing, exiting) itself -- it returns structured
results and raises a typed exception; each caller decides how to surface
that in its own idiom (the CLI via Rich/typer.Exit, the library by letting
the exception propagate).

See docs/plans/2026-09-24-cli-native-packaging-default-on.md, approach
sections 2-4, for the full design this module implements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NativeIntent = Literal["default", "require", "disable"]

# `abi_actual` comes from the companion's own `abi_version()` call -- an
# installed third-party artifact, not something the engine or CLI controls --
# so it is untrusted for direct display (known failure mode: an over-long or
# non-printable value; see the plan's "Known failure modes" section).
_ABI_DISPLAY_MAX_LEN = 200

# The four strategies the unified slice currently admits (plan build-time
# correction #3): deterministic-faker/categorical/bucket_perturb/group_key are
# NOT in today's admitted scope, so the static eligibility predicate below
# must not treat them as native-capable.
_NATIVE_STRATEGIES = frozenset({"passthrough", "redact", "truncate", "hash"})


class NativeGateError(Exception):
    """A fail-closed refusal from the shared native gate.

    Raised at one of three points (plan approach 2's Stage 0/1/2): before
    dispatch for a `--native`-incompatible shape or an absent/broken
    companion, or after a run for `--native` with no compiled-kernel
    evidence. Every case here is something the caller can fix by changing
    the request (drop `--native`, fix the install, rerun with
    `--no-native`) rather than a CLI/engine defect -- both call sites
    classify it as a usage-level refusal, not a runtime crash.
    """

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PreGateResult:
    """What the caller should do before invoking `run_pipeline`."""

    unified_slice_enabled: bool
    info_message: str | None = None
    warn_message: str | None = None


@dataclass(frozen=True)
class RouteClassification:
    """The three-state native route indicator (plan approach 4), scoped to
    whether the run was even a unified-slice candidate.

    `applicable` is True only for a non-chunked, mask-only run that actually
    reached the `full_frame` execution mode (a genuine unified-slice
    candidate); `state` is one of "native" / "unified_slice" / "pandas" when
    `applicable`, else `None`. `label` is always populated -- the
    human-readable route string for the run summary and JSON record.
    """

    applicable: bool
    state: Literal["native", "unified_slice", "pandas"] | None
    label: str


def _probe_status() -> Any:
    from decoy_engine import native_companion_status

    return native_companion_status()


def sanitize_abi(value: str | None) -> str | None:
    """Bound and printable-filter an untrusted `abi_actual` string.

    Never raises on a malformed value: caps length first (so a pathological
    multi-megabyte string is not scanned character-by-character) and then
    drops non-printable characters, per the plan's "Unsanitized ABI string in
    output" known failure mode.
    """
    if value is None:
        return None
    truncated = value[:_ABI_DISPLAY_MAX_LEN]
    return "".join(ch for ch in truncated if ch.isprintable())


def _remediation(reason: str) -> str:
    if reason == "absent":
        return "install the decoy-cli[native] extra, or see docs/native/supported-matrix.md"
    return (
        "reinstall a decoy-engine-native companion matching this engine's ABI, "
        "or rerun with --no-native to use the legacy pandas adapter"
    )


def is_unified_slice_candidate(*, chunked: bool, any_generate: bool) -> bool:
    """The COARSE, pre-run candidate check: non-chunked and mask-only.

    This is deliberately cheaper than `static_native_eligibility` -- it is
    what Stage 0 uses to reject `--native --chunked` and `--native` on a
    generate/mixed config before any dispatch (plan approach 2), without
    knowing yet whether the shape will actually be admitted."""
    return not chunked and not any_generate


def static_native_eligibility(config_dict: dict[str, Any]) -> bool:
    """Config-shape-only static approximation of "would this job's admission
    even reach the companion-health gate": a single non-FK Parquet mask
    table, every column strategy in the four the unified slice currently
    admits, at least one `hash` column (the only strategy admission gates on
    companion health for -- see `_unified_slice_admission.py`'s
    `hash_columns` check), and no validators/quarantine.

    This is the SAME "config-shape half" of the eligibility predicate
    `decoy preflight`'s labeled-static-possibility line uses (plan approach
    4, open question 5): it cannot see the resolved route, the source
    profile, or the resident Arrow table, so it is an approximation, not a
    guarantee. Used to scope the default-intent broken-companion fail-closed
    check (and the absent-companion info hint) to jobs that could plausibly
    have wanted native, so an unrelated FK or passthrough-only job never
    trips on a broken companion it was never going to use.
    """
    tables = config_dict.get("tables")
    if not isinstance(tables, list) or len(tables) != 1:
        return False
    table = tables[0]
    if not isinstance(table, dict) or not table.get("columns"):
        return False
    if config_dict.get("relationships"):
        return False
    if config_dict.get("validators"):
        return False
    columns = table.get("columns")
    if not isinstance(columns, list) or not columns:
        return False
    strategies = {c.get("strategy") for c in columns if isinstance(c, dict)}
    if not strategies <= _NATIVE_STRATEGIES:
        return False
    if "hash" not in strategies:
        return False
    name = table.get("name")
    sources = config_dict.get("sources")
    source = sources.get(name) if isinstance(sources, dict) else None
    if not isinstance(source, dict):
        return False
    fmt = source.get("format")
    path = source.get("path")
    is_parquet = fmt == "parquet" or (
        isinstance(path, str) and path.lower().endswith((".parquet", ".pq"))
    )
    return bool(is_parquet)


def pre_execution_gate(
    *,
    intent: NativeIntent,
    chunked: bool,
    any_generate: bool,
    config_dict: dict[str, Any],
    status: Any = None,
) -> PreGateResult:
    """Resolve `intent` + the companion probe into what to pass
    `run_pipeline`, before it is ever called. May raise `NativeGateError`
    (Stage 0/1 of approach 2, and the broken-companion classification of
    approach 3). `status` is accepted for test injection; omit it to probe
    the real companion."""
    candidate = is_unified_slice_candidate(chunked=chunked, any_generate=any_generate)

    if intent == "require":
        if not candidate:
            raise NativeGateError(
                "--native applies only to a non-chunked, mask-only run: this "
                "invocation is chunked or includes a generate table, neither of "
                "which ever routes through the unified slice, so it could never "
                "show compiled-kernel evidence. Drop --native, or drop --chunked "
                "/ the generate table.",
                code="native_require_not_a_candidate",
            )
        if status is None:
            status = _probe_status()
        if not status.ok:
            raise NativeGateError(
                "--native requires a healthy decoy-engine-native companion, but "
                f"the probe reports {status.reason!r} ({_remediation(status.reason)}).",
                code=f"native_require_{status.reason}",
            )
        return PreGateResult(unified_slice_enabled=True)

    if intent == "disable":
        warn_message = None
        if candidate:
            if status is None:
                status = _probe_status()
            if status.present and not status.ok:
                warn_message = (
                    "the decoy-engine-native companion is present but not usable "
                    f"({status.reason}); moot here since --no-native already forces "
                    "the legacy pandas adapter."
                )
        return PreGateResult(unified_slice_enabled=False, warn_message=warn_message)

    # intent == "default": inherit the engine's own default (unified slice
    # stays enabled; admission decides). Only scope the companion
    # classification to a job that could plausibly have wanted native, so an
    # unrelated job is never blocked (or hinted at) by an install it would
    # never touch.
    if not candidate or not static_native_eligibility(config_dict):
        return PreGateResult(unified_slice_enabled=True)
    if status is None:
        status = _probe_status()
    if status.reason == "absent":
        return PreGateResult(
            unified_slice_enabled=True,
            info_message=(
                "native acceleration is not installed; install the decoy-cli[native] "
                "extra (or see docs/native/supported-matrix.md) to enable it. "
                "Running on the Python fallback."
            ),
        )
    if not status.ok:
        # Present but broken (abi-mismatch / kat-corrupt / load-error): a
        # deployment defect, not portable-package operation -- fail closed by
        # default rather than silently degrade to the pandas oracle (plan
        # approach 3's rationale). `--no-native` is the documented rollback.
        raise NativeGateError(
            "the decoy-engine-native companion is present but not usable "
            f"({status.reason}); {_remediation(status.reason)}.",
            code=f"native_companion_{status.reason}",
        )
    return PreGateResult(unified_slice_enabled=True)


def classify_route(
    *,
    chunked: bool,
    any_generate: bool,
    resolved_substrate: str | None,
    quality_metrics: dict[str, Any] | None,
) -> RouteClassification:
    """The three-state native route indicator, scoped to candidacy (plan
    approach 4). Reads evidence (`unified_slice_activation` +
    `compiled_kernel_executed`), never the requested flag, so a rerouted job
    is never mislabeled.

    `--chunked` runs have no `ExecutionResult` (the chunked path streams
    per-chunk and returns nothing to classify), so `quality_metrics` is
    `None` for them and the label is built from `resolved_substrate` alone
    (build-time correction #1: never hardcode "pandas" -- report the
    substrate actually resolved for this run)."""
    if chunked:
        return RouteClassification(
            applicable=False,
            state=None,
            label=f"{resolved_substrate or 'pandas'} chunked stream",
        )

    qm = quality_metrics or {}
    # Build-time correction #2: the engine's route telemetry keys this
    # `execution_mode`, not `route`.
    execution_mode = (qm.get("execution") or {}).get("execution_mode")

    if any_generate:
        label = execution_mode or "n/a (not a unified-slice candidate)"
        return RouteClassification(applicable=False, state=None, label=label)

    if execution_mode is not None and execution_mode != "full_frame":
        return RouteClassification(applicable=False, state=None, label=execution_mode)

    activation = qm.get("unified_slice_activation")
    if activation is None:
        return RouteClassification(applicable=True, state="pandas", label="pandas (legacy adapter)")

    nodes = activation.get("nodes") or {}
    if any(node.get("compiled_kernel_executed") for node in nodes.values()):
        return RouteClassification(
            applicable=True, state="native", label="native (compiled kernel)"
        )
    return RouteClassification(
        applicable=True, state="unified_slice", label="unified slice (no compiled kernel)"
    )


def post_run_verify(*, intent: NativeIntent, route: RouteClassification) -> None:
    """Stage 2 of approach 2: after the run, before either write point,
    assert `--native` actually got positive compiled-kernel evidence. A
    no-op for `default`/`disable` intent -- those never promise native
    happened, so there is nothing to verify."""
    if intent != "require":
        return
    if route.state == "native":
        return
    raise NativeGateError(
        "--native required a compiled kernel to execute, but this run finished "
        f"via {route.label!r} with no positive compiled-kernel evidence; no output "
        "was written.",
        code="native_require_no_evidence",
    )


__all__ = [
    "NativeGateError",
    "NativeIntent",
    "PreGateResult",
    "RouteClassification",
    "classify_route",
    "is_unified_slice_candidate",
    "post_run_verify",
    "pre_execution_gate",
    "sanitize_abi",
    "static_native_eligibility",
]
