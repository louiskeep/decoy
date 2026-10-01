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

Known, accepted gap (post-build-time correction, remediation round 1): admission
gates a table's companion dependency PER OPERATOR (`native_kernel_availability()`
-- a companion missing only the additive raw-hex symbol still runs hash /
categorical / bucket_perturb natively and declines only group_key). That
per-kernel probe is not re-exported at the engine's public boundary (only
`native_companion_status()`'s blanket ok/not-ok is), and the plan's own
reuse-only mandate ("reuse the engine's native_companion_status() probe ...
do not re-implement companion detection in the CLI") argues against reaching
into the engine's private `execution.native._companion_status` module to get
it. This module therefore gates on the blanket probe: a companion that is
only PARTIALLY broken (e.g. missing raw-hex only) is treated as fully broken
here, which can fail closed a job that the engine would have run natively.
That is the safe direction (over-conservative, never a silent false native
claim), not the unsafe one -- but it is a real, known precision gap, not a
design decision to hide.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Literal

NativeIntent = Literal["default", "require", "disable"]

# `abi_actual` comes from the companion's own `abi_version()` call -- an
# installed third-party artifact, not something the engine or CLI controls --
# so it is untrusted for direct display (known failure mode: an over-long or
# non-printable value; see the plan's "Known failure modes" section).
_ABI_DISPLAY_MAX_LEN = 200

# The full native-admitted strategy set, mirroring the engine's CURRENT
# `ALLOWED_OPERATOR_IDS` (`_unified_slice_admission.py`) via
# `OPERATOR_ID_BY_STRATEGY`'s strategy-name keys. Remediation round 1: the
# original build hardcoded a 4-strategy set (passthrough/redact/truncate/
# hash) per the plan's own build-time correction #3, which was accurate when
# the plan's PLAN-gate ran but had already been overtaken by engine main
# landing native_categorical/native_bucket_perturb/native_group_key days
# earlier -- a stale-plan-fact bug, not a build mistake, but the CLI must
# match the engine it actually ships against, not a snapshot of it. Keep
# this set in lockstep with the engine's admission allowlist; a mismatch
# either falsely blocks an admitted shape (this set too narrow) or
# falsely offers eligibility for a shape the engine declines (too wide).
_NATIVE_STRATEGIES = frozenset(
    {"passthrough", "redact", "truncate", "hash", "categorical", "bucket_perturb", "group_key"}
)

# The subset of `_NATIVE_STRATEGIES` whose native execution needs the
# compiled companion loadable at all (mirrors
# `_COMPANION_DEPENDENT_OPERATOR_IDS`): passthrough/redact/truncate run
# native via the coordinator alone, with no companion involvement (state
# (b), "unified slice (no compiled kernel)"). A table needs company health
# only when it uses one of THESE.
_COMPANION_DEPENDENT_STRATEGIES = frozenset({"hash", "categorical", "bucket_perturb", "group_key"})


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


class _NativeProbeUnavailable(Exception):
    """The installed `decoy-engine` predates `native_companion_status()`
    (added after the `>=0.5.0` floor was tagged, per the same
    still-labeled-0.5.0 situation `run.py`'s DE-02 comment documents for
    `keyprovider`). Caught internally by `pre_execution_gate` -- never
    escapes this module."""


def _probe_status() -> Any:
    import decoy_engine

    probe = getattr(decoy_engine, "native_companion_status", None)
    if probe is None:
        raise _NativeProbeUnavailable
    return probe()


_NON_STRING_ABI_MARKER = "<non-string value>"


def sanitize_abi(value: Any) -> str | None:
    """Bound and printable-filter an untrusted `abi_actual` / `version` value.

    Never raises on a malformed value. The value comes straight from the
    companion's own `abi_version()` call, so a broken install can hand back
    anything: a non-string yields the fixed `_NON_STRING_ABI_MARKER` rather
    than a TypeError (the diagnostic commands must survive exactly that
    case). A string is capped in length first (so a pathological
    multi-megabyte string is not scanned character-by-character) and then
    stripped of non-printable characters, per the plan's "Unsanitized ABI
    string in output" known failure mode.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return _NON_STRING_ABI_MARKER
    truncated = value[:_ABI_DISPLAY_MAX_LEN]
    return "".join(ch for ch in truncated if ch.isprintable())


def _remediation(reason: str) -> str:
    if reason == "absent":
        # No `native` extra and no published direct-install artifact exist
        # yet (see the plan's packaging section + `decoy explain native`) --
        # point at the topic for current status rather than naming an
        # install command that would fail today.
        return "see `decoy explain native` for current install status"
    return (
        "reinstall a decoy-engine-native companion matching this engine's ABI, "
        "or force the legacy pandas adapter (--no-native on the CLI, "
        "native=False for decoy.mask())"
    )


def is_unified_slice_candidate(*, chunked: bool, any_generate: bool) -> bool:
    """The COARSE, pre-run candidate check: non-chunked and mask-only.

    This is deliberately cheaper than `static_native_eligibility` -- it is
    what Stage 0 uses to reject `--native --chunked` and `--native` on a
    generate/mixed config before any dispatch (plan approach 2), without
    knowing yet whether the shape will actually be admitted."""
    return not chunked and not any_generate


def _has_when_gate(column: dict[str, Any]) -> bool:
    """Mirrors the engine's own `_has_when_gate` (`_unified_slice_admission.py`):
    a `when:` predicate gates masking to matching rows only, which the
    coordinator does not implement, so any column carrying one declines."""
    when = column.get("when")
    return when is not None and when != {}


def source_is_materialized(entry: Any) -> bool:
    """Whether the CLI loader (`decoy.cli.run._load_sources_from_config`)
    reads this `sources:` entry into a resident table. The loader calls this
    same predicate, so the static eligibility check and the tables actually
    handed to `run_pipeline` cannot drift apart."""
    return isinstance(entry, dict) and isinstance(entry.get("path"), str)


# Mirrors the engine's `_ADMITTED_SOURCE_FORMATS` (unified-slice admission).
_NATIVE_SOURCE_FORMATS = frozenset({"parquet", "csv", "fixed_width"})


def static_native_eligibility(config_dict: dict[str, Any]) -> bool:
    """Config-shape-only static approximation of "would this job's admission
    even reach the companion-health gate": a single non-FK csv/parquet/fixed_width
    file mask table, every column strategy in the set the unified slice currently
    admits (`_NATIVE_STRATEGIES`), at least one companion-dependent column
    (hash/categorical/bucket_perturb/group_key -- the only strategies
    admission gates on companion health for for `_COMPANION_DEPENDENT_
    STRATEGIES`), and none of the config-visible declines
    `cheap_admission`/`resident_contract_admission` check: validators,
    quarantine, run_storm, a `vault: true` column, table-level `transforms`,
    or a per-column `when:` gate.

    This is the SAME "config-shape half" of the eligibility predicate
    `decoy preflight`'s labeled-static-possibility line uses (plan approach
    4, open question 5): it cannot see the resolved route, the source
    profile, the resident Arrow table, or a live `--vault` writer (that
    needs the caller's own runtime state -- see `pre_execution_gate`'s
    `vault_active` parameter), so it is an approximation, not a guarantee.
    Used to scope the default-intent broken-companion fail-closed check
    (and the absent-companion info hint) to jobs that could plausibly have
    wanted native, so an unrelated FK, transform, quarantine, or
    passthrough-only job never trips on a broken companion it was never
    going to use.
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
    if config_dict.get("quarantine"):
        return False
    if config_dict.get("run_storm"):
        return False
    if table.get("transforms"):
        return False
    columns = table.get("columns")
    if not isinstance(columns, list) or not columns:
        return False
    if not all(isinstance(c, dict) for c in columns):
        return False
    if any(c.get("vault") for c in columns):
        return False
    if any(_has_when_gate(c) for c in columns):
        return False
    if any(
        c.get("strategy") == "categorical"
        and not (c.get("deterministic") or c.get("allow_collisions"))
        for c in columns
    ):
        # Mirrors `is_deterministic_categorical` (`_operator_config_
        # rejections.py`): a categorical column defaults to the RANDOM path
        # (`deterministic: false`), which the compiler's own
        # `categorical_not_deterministic` rejection declines from native
        # regardless of companion health -- a plain `strategy: categorical`
        # column (no `deterministic`/`allow_collisions` override) is common
        # and must not be treated as eligible.
        return False
    strategies = {c.get("strategy") for c in columns}
    if not strategies <= _NATIVE_STRATEGIES:
        return False
    if not strategies & _COMPANION_DEPENDENT_STRATEGIES:
        return False
    name = table.get("name")
    sources = config_dict.get("sources")
    if not isinstance(sources, dict):
        return False
    materialized = {key for key, entry in sources.items() if source_is_materialized(entry)}
    if materialized != {name}:
        # Admission requires the resident sources to be EXACTLY {table}
        # (`_unified_slice_admission.py`'s `set(caller_sources) != {table}`
        # decline). `caller_sources` is what the CLI loader actually
        # materialized, not every declared key: a declared entry the loader
        # skips (no `path`, e.g. a cloud reference) never reaches admission,
        # so comparing raw declared keys here would wrongly decline.
        return False
    source = sources[name]
    if not isinstance(source, dict):
        return False
    if source.get("type") != "file":
        return False
    # Exact match on the declared format, matching admission's own check
    # (`source_descriptor.get("format") not in _ADMITTED_SOURCE_FORMATS`) --
    # no path-suffix fallback, so the extension never decides eligibility
    # (the engine goes by the declared format, not the extension).
    return source.get("format") in _NATIVE_SOURCE_FORMATS


def pre_execution_gate(
    *,
    intent: NativeIntent,
    chunked: bool,
    any_generate: bool,
    config_dict: dict[str, Any],
    vault_active: bool = False,
    status: Any = None,
) -> PreGateResult:
    """Resolve `intent` + the companion probe into what to pass
    `run_pipeline`, before it is ever called. May raise `NativeGateError`
    (Stage 0/1 of approach 2, and the broken-companion classification of
    approach 3). `status` is accepted for test injection; omit it to probe
    the real companion. `vault_active` is whether the CALLER actually built
    a vault writer for this run (`decoy run --vault`) -- admission declines
    a live vault writer regardless of config shape, so the default-intent
    scoping below needs this precise runtime fact, not just a `vault: true`
    column marker (`static_native_eligibility` already checks that marker
    as its own config-shape proxy; this ANDs the exact answer on top)."""
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
        if vault_active:
            # Admission always declines a job with a live vault writer
            # (`resident_contract_admission`), regardless of companion
            # health -- a Stage 0-style refusal, not a companion check.
            raise NativeGateError(
                "--native cannot be satisfied together with --vault: the "
                "unified slice always declines a job with a live vault writer, "
                "so this run could never show compiled-kernel evidence. Drop "
                "--native, or drop --vault.",
                code="native_require_vault_active",
            )
        if status is None:
            try:
                status = _probe_status()
            except _NativeProbeUnavailable:
                raise NativeGateError(
                    "--native needs a decoy-engine build with the native probe "
                    "(native_companion_status); the installed decoy-engine "
                    "predates it. Upgrade decoy-engine, or drop --native.",
                    code="native_require_engine_too_old",
                ) from None
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
            try:
                if status is None:
                    status = _probe_status()
                if status.present and not status.ok:
                    warn_message = (
                        "the decoy-engine-native companion is present but not usable "
                        f"({status.reason}); moot here since disabling native already "
                        "forces the legacy pandas adapter."
                    )
            except _NativeProbeUnavailable:
                pass
        return PreGateResult(unified_slice_enabled=False, warn_message=warn_message)

    # intent == "default": inherit the engine's own default (unified slice
    # stays enabled; admission decides). Only scope the companion
    # classification to a job that could plausibly have wanted native, so an
    # unrelated job is never blocked (or hinted at) by an install it would
    # never touch.
    if vault_active or not candidate or not static_native_eligibility(config_dict):
        return PreGateResult(unified_slice_enabled=True)
    try:
        if status is None:
            status = _probe_status()
    except _NativeProbeUnavailable:
        # An engine this old predates the whole native lane too, so there is
        # nothing to gate -- collapse to the same no-op as "not a candidate".
        return PreGateResult(unified_slice_enabled=True)
    if status.reason == "absent":
        return PreGateResult(
            unified_slice_enabled=True,
            info_message=(
                "native acceleration is not installed; run `decoy explain native` "
                "for current install status. Running on the Python fallback."
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


def run_pipeline_kwargs(gate_result: PreGateResult) -> dict[str, bool]:
    """The `run_pipeline` kwargs to pass for `gate_result`, capability-detected
    against the INSTALLED engine (HIGH remediation, round 3): `unified_slice_
    enabled=True` is already the engine's own default, so it is passed only to
    force it `False` (`--no-native` / `native=False`) -- and even then, only
    if the installed `run_pipeline` actually accepts that parameter.

    `unified_slice_enabled` landed on engine main (2026-09-15) after the
    `decoy-engine>=0.5.0` floor was tagged (2026-07-24, per the same still-
    labeled-0.5.0 situation `run.py`'s DE-02 comment documents for
    `keyprovider`), so an in-range 0.5.0 install can genuinely lack it. Before
    this fix, `--no-native` -- the documented ROLLBACK for when something
    looks wrong -- was the one path guaranteed to crash such an install with a
    `TypeError`, while doing nothing (the default path) or requiring native
    (which fails on its own missing-capability check first) both degraded
    cleanly. An engine without the parameter also has no unified-slice lane at
    all, so omitting it is not a compromise: that engine already behaves as if
    native were disabled, unconditionally.

    Both `decoy run` and `decoy.mask()` call this instead of building the
    kwargs dict themselves, so neither can independently regress this."""
    if gate_result.unified_slice_enabled:
        return {}
    from decoy_engine import run_pipeline

    if "unified_slice_enabled" not in inspect.signature(run_pipeline).parameters:
        return {}
    return {"unified_slice_enabled": False}


__all__ = [
    "NativeGateError",
    "NativeIntent",
    "PreGateResult",
    "RouteClassification",
    "classify_route",
    "is_unified_slice_candidate",
    "post_run_verify",
    "pre_execution_gate",
    "run_pipeline_kwargs",
    "sanitize_abi",
    "source_is_materialized",
    "static_native_eligibility",
]
