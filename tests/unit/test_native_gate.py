"""Unit tests for `decoy._native_gate` (Phase 3.1: CLI native
packaging default-on-when-present).

These exercise the shared gate module directly, with injected
`NativeCompanionStatus` values and synthetic `quality_metrics` dicts, rather
than a real compiled `decoy-engine-native` companion (unavailable in this
dev/test environment -- no paired PyPI release exists yet, per the plan's
packaging section). `tests/e2e/test_run_native.py` and
`tests/e2e/test_mask_api_native.py` cover the same behavior wired end-to-end
through `decoy run` / `decoy.mask()`, using the REAL (absent) companion in
this environment plus targeted monkeypatching of
`decoy_engine.native_companion_status` for the CLI-side gate decision.

See docs/plans/2026-09-24-cli-native-packaging-default-on.md, "Acceptance
tests (define-first)".
"""

from __future__ import annotations

import pytest
from decoy_engine import NativeCompanionStatus

from decoy._native_gate import (
    NativeGateError,
    _NativeProbeUnavailable,
    classify_route,
    is_unified_slice_candidate,
    post_run_verify,
    pre_execution_gate,
    sanitize_abi,
    static_native_eligibility,
)

_ABI = "decoy-native-abi-2"


def _status(
    reason: str, *, present: bool, ok: bool, abi_actual: str | None = None
) -> NativeCompanionStatus:
    return NativeCompanionStatus(
        present=present,
        ok=ok,
        abi_expected=_ABI,
        abi_actual=abi_actual,
        version="9.9.9" if present else None,
        reason=reason,
        cause=None,
    )


_ABSENT = _status("absent", present=False, ok=False)
_PRESENT_OK = _status("present-ok", present=True, ok=True, abi_actual=_ABI)
_ABI_MISMATCH = _status("abi-mismatch", present=True, ok=False, abi_actual="decoy-native-abi-1")
_KAT_CORRUPT = _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI)
_LOAD_ERROR = _status("load-error", present=True, ok=False, abi_actual=_ABI)


def _eligible_config() -> dict:
    """Single non-FK Parquet mask table, passthrough + hash columns."""
    return {
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash"},
                ],
            }
        ],
        "sources": {"customers": {"type": "file", "format": "parquet", "path": "in.parquet"}},
    }


# ---------------------------------------------------------------------------
# static_native_eligibility
# ---------------------------------------------------------------------------


def test_eligible_config_is_eligible():
    assert static_native_eligibility(_eligible_config()) is True


def test_table_without_columns_not_eligible():
    config = _eligible_config()
    config["tables"] = [{"name": "customers", "row_count": 5, "generate_columns": []}]
    assert static_native_eligibility(config) is False


def test_empty_columns_list_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"] = []
    assert static_native_eligibility(config) is False


def test_non_dict_column_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"].append("not-a-dict")
    assert static_native_eligibility(config) is False


def test_missing_source_entry_not_eligible():
    config = _eligible_config()
    config["sources"] = {}
    assert static_native_eligibility(config) is False


def test_non_dict_source_entry_not_eligible():
    config = _eligible_config()
    config["sources"]["customers"] = "not-a-dict"
    assert static_native_eligibility(config) is False


def test_non_list_columns_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"] = "not-a-list"
    assert static_native_eligibility(config) is False


def test_all_seven_native_strategies_at_once_is_eligible():
    """Mutation regression (Codex round 3): `strategies <= _NATIVE_STRATEGIES`
    must stay a subset-or-EQUAL check, not a strict subset -- a table using
    every currently-admitted strategy at once (the equality case) is still
    eligible."""
    config = _eligible_config()
    config["tables"][0]["columns"] = [
        {"name": "c1", "strategy": "passthrough"},
        {"name": "c2", "strategy": "redact"},
        {"name": "c3", "strategy": "truncate"},
        {"name": "c4", "strategy": "hash"},
        {"name": "c5", "strategy": "categorical", "deterministic": True},
        {"name": "c6", "strategy": "bucket_perturb"},
        {"name": "c7", "strategy": "group_key"},
    ]
    assert static_native_eligibility(config) is True


def test_probe_status_raises_when_engine_lacks_the_symbol(monkeypatch):
    """Hits `_probe_status()`'s own missing-symbol branch directly (the
    other engine-too-old tests monkeypatch `_probe_status` itself, which
    bypasses this line)."""
    import decoy_engine

    from decoy._native_gate import _probe_status

    monkeypatch.delattr(decoy_engine, "native_companion_status", raising=False)
    with pytest.raises(_NativeProbeUnavailable):
        _probe_status()


def test_two_tables_not_eligible():
    config = _eligible_config()
    config["tables"].append({"name": "orders", "columns": [{"name": "x", "strategy": "redact"}]})
    assert static_native_eligibility(config) is False


def test_relationships_not_eligible():
    config = _eligible_config()
    config["relationships"] = [{"parent": "customers", "child": "customers", "columns": []}]
    assert static_native_eligibility(config) is False


def test_validators_not_eligible():
    config = _eligible_config()
    config["validators"] = [{"kind": "not_null", "columns": ["id"]}]
    assert static_native_eligibility(config) is False


def test_quarantine_not_eligible():
    config = _eligible_config()
    config["quarantine"] = {"path": "quarantine.csv"}
    assert static_native_eligibility(config) is False


def test_run_storm_not_eligible():
    config = _eligible_config()
    config["run_storm"] = True
    assert static_native_eligibility(config) is False


def test_vault_column_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"][1]["vault"] = True
    assert static_native_eligibility(config) is False


def test_non_parquet_source_not_eligible():
    config = _eligible_config()
    config["sources"]["customers"]["format"] = "csv"
    config["sources"]["customers"]["path"] = "in.csv"
    assert static_native_eligibility(config) is False


def test_no_companion_dependent_column_not_eligible():
    """passthrough/redact/truncate run native WITHOUT the companion (state
    b) -- eligibility (whether the companion-health gate is even reached)
    requires at least one companion-dependent strategy."""
    config = _eligible_config()
    config["tables"][0]["columns"] = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "note", "strategy": "redact"},
    ]
    assert static_native_eligibility(config) is False


def test_disallowed_strategy_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"].append({"name": "first_name", "strategy": "faker"})
    assert static_native_eligibility(config) is False


@pytest.mark.parametrize("strategy", ["categorical", "bucket_perturb", "group_key"])
def test_other_companion_dependent_strategies_are_eligible(strategy):
    """Remediation (Codex/dennis round 1): the engine's admitted set widened
    to 7 strategies (`_unified_slice_admission.ALLOWED_OPERATOR_IDS`) before
    this plan's own PLAN gate ran; the original build's 4-strategy hardcode
    was already stale. hash/categorical/bucket_perturb/group_key are ALL
    companion-dependent (`_COMPANION_DEPENDENT_OPERATOR_IDS`), so any one of
    them alone must make a config eligible, not just hash."""
    config = _eligible_config()
    column: dict = {"name": "email", "strategy": strategy}
    if strategy == "categorical":
        # A plain `categorical` column defaults to the random, non-native
        # path (see test_categorical_requires_determinism_to_be_eligible);
        # this test is about the STRATEGY-SET check, not the determinism one.
        column["deterministic"] = True
    config["tables"][0]["columns"] = [
        {"name": "id", "strategy": "passthrough"},
        column,
    ]
    assert static_native_eligibility(config) is True


def test_categorical_requires_determinism_to_be_eligible():
    """A plain `strategy: categorical` column (the common case) defaults to
    `deterministic: false`, which the compiler's own `categorical_not_
    deterministic` rejection declines from native regardless of companion
    health (dennis round 3, mirroring `is_deterministic_categorical`)."""
    config = _eligible_config()
    config["tables"][0]["columns"] = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "email", "strategy": "categorical"},
    ]
    assert static_native_eligibility(config) is False


def test_categorical_with_allow_collisions_is_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"] = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "email", "strategy": "categorical", "allow_collisions": True},
    ]
    assert static_native_eligibility(config) is True


def test_transforms_not_eligible():
    config = _eligible_config()
    config["tables"][0]["transforms"] = [{"kind": "some_transform"}]
    assert static_native_eligibility(config) is False


def test_when_gate_not_eligible():
    config = _eligible_config()
    config["tables"][0]["columns"][1]["when"] = {"column": "id", "equals": "C1"}
    assert static_native_eligibility(config) is False


def test_non_file_source_type_not_eligible():
    config = _eligible_config()
    config["sources"]["customers"]["type"] = "database"
    assert static_native_eligibility(config) is False


def test_missing_format_field_not_eligible_even_with_parquet_path():
    """Remediation (dennis round 2): admission checks the DECLARED `format`
    field exactly (`source_descriptor.get("format") != "parquet"`), never a
    path-suffix inference -- a `.parquet`-suffixed path with no (or a
    mismatched) format field is not eligible, matching the engine exactly."""
    config = _eligible_config()
    del config["sources"]["customers"]["format"]
    config["sources"]["customers"]["path"] = "in.parquet"
    assert static_native_eligibility(config) is False


def test_mislabeled_format_not_eligible_even_with_parquet_path():
    config = _eligible_config()
    config["sources"]["customers"]["format"] = "csv"
    config["sources"]["customers"]["path"] = "in.parquet"
    assert static_native_eligibility(config) is False


def test_extra_declared_source_not_eligible():
    """Remediation (dennis round 2): admission requires the resident
    sources to be EXACTLY {table} -- an extra declared source (even for a
    table that plays no other role here) is the config-visible half of
    that same decline."""
    config = _eligible_config()
    config["sources"]["orders"] = {"type": "file", "format": "parquet", "path": "orders.parquet"}
    assert static_native_eligibility(config) is False


def test_extra_declared_source_without_path_still_eligible():
    """dennis re-verify MEDIUM-1: admission compares the MATERIALIZED
    caller sources, and the CLI loader (`_load_sources_from_config`) skips
    any entry with no string `path` (e.g. a cloud source reference). An
    extra declared-but-unloaded source never reaches `caller_sources`, so
    it must not flip the static check to "not eligible"."""
    config = _eligible_config()
    config["sources"]["archive"] = {"type": "s3", "bucket": "b", "key": "k.parquet"}
    assert static_native_eligibility(config) is True


def test_extra_declared_source_agrees_with_cli_loader(tmp_path):
    """The eligibility check and the real loader must agree on which
    sources get materialized: the loader yields exactly `{table}` here."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from decoy.cli.run import _load_sources_from_config

    pq.write_table(pa.table({"id": [1], "email": ["a@x"]}), tmp_path / "in.parquet")
    config = _eligible_config()
    config["sources"]["archive"] = {"type": "s3", "bucket": "b", "key": "k.parquet"}
    assert set(_load_sources_from_config(config, tmp_path)) == {"customers"}
    assert static_native_eligibility(config) is True


def test_mask_table_source_without_path_not_eligible():
    """The mask table's own source must be one the loader materializes;
    without a `path` it never becomes a resident table, and admission
    declines a missing source."""
    config = _eligible_config()
    del config["sources"]["customers"]["path"]
    assert static_native_eligibility(config) is False


# ---------------------------------------------------------------------------
# sanitize_abi
# ---------------------------------------------------------------------------


def test_sanitize_abi_none_passthrough():
    assert sanitize_abi(None) is None


def test_sanitize_abi_normal_string_unchanged():
    assert sanitize_abi(_ABI) == _ABI


def test_sanitize_abi_caps_length():
    huge = "x" * 10_000
    result = sanitize_abi(huge)
    assert result is not None
    assert len(result) <= 200


def test_sanitize_abi_strips_non_printable():
    result = sanitize_abi("abi\x00\x01-2\n")
    assert result is not None
    assert "\x00" not in result
    assert "\x01" not in result


@pytest.mark.parametrize("bad", [2, 2.5, b"decoy-native-abi-2", ["abi"], {"abi": 2}, object()])
def test_sanitize_abi_non_string_returns_bounded_marker(bad):
    """dennis re-verify MEDIUM-2: `abi_actual`/`version` come from the
    companion's own `abi_version()` call, which is untrusted on a broken
    install. A non-string must yield a fixed marker, never a TypeError, so
    `decoy info` / `decoy preflight` can still diagnose the install."""
    result = sanitize_abi(bad)
    assert result == "<non-string value>"


# ---------------------------------------------------------------------------
# is_unified_slice_candidate
# ---------------------------------------------------------------------------


def test_candidate_requires_non_chunked_and_mask_only():
    assert is_unified_slice_candidate(chunked=False, any_generate=False) is True
    assert is_unified_slice_candidate(chunked=True, any_generate=False) is False
    assert is_unified_slice_candidate(chunked=False, any_generate=True) is False
    assert is_unified_slice_candidate(chunked=True, any_generate=True) is False


# ---------------------------------------------------------------------------
# classify_route
# ---------------------------------------------------------------------------


def test_classify_route_chunked_reports_resolved_substrate():
    route = classify_route(
        chunked=True, any_generate=False, resolved_substrate="polars", quality_metrics=None
    )
    assert route.applicable is False
    assert route.state is None
    assert route.label == "polars chunked stream"


def test_classify_route_chunked_defaults_to_pandas_label_when_substrate_none():
    route = classify_route(
        chunked=True, any_generate=False, resolved_substrate=None, quality_metrics=None
    )
    assert route.label == "pandas chunked stream"


def test_classify_route_generate_only_reports_execution_mode():
    route = classify_route(
        chunked=False,
        any_generate=True,
        resolved_substrate=None,
        quality_metrics={"execution": {"execution_mode": "sequential"}},
    )
    assert route.applicable is False
    assert route.state is None
    assert route.label == "sequential"


def test_classify_route_generate_only_without_execution_metrics_is_neutral():
    route = classify_route(
        chunked=False, any_generate=True, resolved_substrate=None, quality_metrics=None
    )
    assert route.applicable is False
    assert route.label == "n/a (not a unified-slice candidate)"


def test_classify_route_non_full_frame_mask_only_reports_execution_mode():
    """A mask-only job that routed out-of-core/sequential (FK fan-out) is
    NOT a unified-slice candidate either -- see plan approach 4's
    "full-frame job" qualifier."""
    route = classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics={"execution": {"execution_mode": "out_of_core"}},
    )
    assert route.applicable is False
    assert route.label == "out_of_core"


def test_classify_route_full_frame_without_activation_is_pandas_legacy():
    route = classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics={"execution": {"execution_mode": "full_frame"}},
    )
    assert route.applicable is True
    assert route.state == "pandas"
    assert route.label == "pandas (legacy adapter)"


def test_classify_route_activation_with_no_compiled_kernel_is_unified_slice_state():
    """Build-time correction P1-2: passthrough/redact/truncate-only jobs
    activate the unified slice WITHOUT the companion; never label this
    'pandas'."""
    route = classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics={
            "execution": {"execution_mode": "full_frame"},
            "unified_slice_activation": {
                "activated": True,
                "nodes": {
                    "n1": {"operator": "native_passthrough", "compiled_kernel_executed": False},
                    "n2": {"operator": "native_redact", "compiled_kernel_executed": False},
                },
            },
        },
    )
    assert route.applicable is True
    assert route.state == "unified_slice"
    assert route.label == "unified slice (no compiled kernel)"
    assert "pandas" not in route.label


def test_classify_route_activation_with_compiled_kernel_is_native():
    route = classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics={
            "execution": {"execution_mode": "full_frame"},
            "unified_slice_activation": {
                "activated": True,
                "nodes": {
                    "n1": {"operator": "native_passthrough", "compiled_kernel_executed": False},
                    "n2": {"operator": "native_keyed_hash", "compiled_kernel_executed": True},
                },
            },
        },
    )
    assert route.applicable is True
    assert route.state == "native"
    assert route.label == "native (compiled kernel)"


# ---------------------------------------------------------------------------
# pre_execution_gate -- require (--native)
# ---------------------------------------------------------------------------


def test_require_rejects_chunked_before_dispatch():
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require", chunked=True, any_generate=False, config_dict={}, status=_ABSENT
        )
    assert exc_info.value.code == "native_require_not_a_candidate"


def test_require_rejects_generate_config_before_dispatch():
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require", chunked=False, any_generate=True, config_dict={}, status=_ABSENT
        )
    assert exc_info.value.code == "native_require_not_a_candidate"


def test_require_never_probes_when_not_a_candidate(monkeypatch):
    """Stage 0 rejects before Stage 1's companion probe ever runs. `_boom`
    is actually installed (L1 fix, Codex round 3): a prior version of this
    test defined it but never wired it in, so it proved nothing about
    probing -- only that the chunked+require combo raises, which the
    dedicated `test_require_rejects_chunked_before_dispatch` already
    covers."""

    def _boom():
        raise AssertionError("probe should not run for a non-candidate --native request")

    monkeypatch.setattr("decoy._native_gate._probe_status", _boom)
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require",
            chunked=True,
            any_generate=False,
            config_dict={},
            status=None,
        )
    assert exc_info.value.code == "native_require_not_a_candidate"


@pytest.mark.parametrize("status", [_ABSENT, _ABI_MISMATCH, _KAT_CORRUPT, _LOAD_ERROR])
def test_require_refuses_absent_or_broken_companion(status):
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require",
            chunked=False,
            any_generate=False,
            config_dict=_eligible_config(),
            status=status,
        )
    assert exc_info.value.code == f"native_require_{status.reason}"


def test_require_proceeds_on_healthy_companion():
    result = pre_execution_gate(
        intent="require",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_PRESENT_OK,
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None
    assert result.warn_message is None


def test_require_refuses_live_vault_writer_before_probing():
    """L5: admission always declines a live vault writer regardless of
    companion health (`resident_contract_admission`), so `--native --vault`
    is a Stage-0-style refusal, not a companion check -- status=None here
    would blow up in `_probe_status()` if the short-circuit were missing."""
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require",
            chunked=False,
            any_generate=False,
            config_dict=_eligible_config(),
            vault_active=True,
            status=None,
        )
    assert exc_info.value.code == "native_require_vault_active"


def test_require_reports_clear_error_when_engine_too_old(monkeypatch):
    def _boom():
        raise _NativeProbeUnavailable

    monkeypatch.setattr("decoy._native_gate._probe_status", _boom)
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="require",
            chunked=False,
            any_generate=False,
            config_dict=_eligible_config(),
        )
    assert exc_info.value.code == "native_require_engine_too_old"


def test_default_collapses_to_noop_when_engine_too_old(monkeypatch):
    def _boom():
        raise _NativeProbeUnavailable

    monkeypatch.setattr("decoy._native_gate._probe_status", _boom)
    result = pre_execution_gate(
        intent="default",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None


def test_disable_swallows_engine_too_old(monkeypatch):
    def _boom():
        raise _NativeProbeUnavailable

    monkeypatch.setattr("decoy._native_gate._probe_status", _boom)
    result = pre_execution_gate(
        intent="disable",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
    )
    assert result.unified_slice_enabled is False
    assert result.warn_message is None


# ---------------------------------------------------------------------------
# pre_execution_gate -- disable (--no-native)
# ---------------------------------------------------------------------------


def test_disable_forces_unified_slice_off():
    result = pre_execution_gate(
        intent="disable",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_PRESENT_OK,
    )
    assert result.unified_slice_enabled is False


def test_disable_warns_on_broken_companion():
    result = pre_execution_gate(
        intent="disable",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_KAT_CORRUPT,
    )
    assert result.unified_slice_enabled is False
    assert result.warn_message is not None
    assert "kat-corrupt" in result.warn_message


def test_disable_does_not_warn_on_absent_companion():
    result = pre_execution_gate(
        intent="disable",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_ABSENT,
    )
    assert result.warn_message is None


def test_disable_on_non_candidate_never_probes():
    # chunked=True -> not a candidate; status=None would blow up in
    # _probe_status() (a real decoy_engine import) if the short-circuit
    # were missing, so passing None here proves the probe never fires.
    result = pre_execution_gate(
        intent="disable", chunked=True, any_generate=False, config_dict={}, status=None
    )
    assert result.unified_slice_enabled is False
    assert result.warn_message is None


# ---------------------------------------------------------------------------
# pre_execution_gate -- default (no flag)
# ---------------------------------------------------------------------------


def test_default_on_non_candidate_never_probes_and_stays_enabled():
    result = pre_execution_gate(
        intent="default", chunked=False, any_generate=True, config_dict={}, status=None
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None


def test_default_on_ineligible_shape_never_probes_and_stays_enabled():
    ineligible = {"tables": [{"name": "t", "columns": [{"name": "c", "strategy": "redact"}]}]}
    result = pre_execution_gate(
        intent="default", chunked=False, any_generate=False, config_dict=ineligible, status=None
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None


def test_default_on_eligible_shape_with_absent_companion_hints_install():
    result = pre_execution_gate(
        intent="default",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_ABSENT,
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is not None
    assert "decoy explain native" in result.info_message


def test_default_on_eligible_shape_with_healthy_companion_is_silent():
    result = pre_execution_gate(
        intent="default",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        status=_PRESENT_OK,
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None
    assert result.warn_message is None


def test_default_on_eligible_shape_with_live_vault_writer_never_probes(monkeypatch):
    """A live `--vault` writer declines admission regardless of config
    shape (`resident_contract_admission`); the default-intent fail-closed
    check must not fire for it even with a broken companion, and must not
    probe at all when `vault_active=True` short-circuits it first."""

    def _boom():
        raise AssertionError("probe should not run when vault_active=True")

    monkeypatch.setattr("decoy._native_gate._probe_status", _boom)
    result = pre_execution_gate(
        intent="default",
        chunked=False,
        any_generate=False,
        config_dict=_eligible_config(),
        vault_active=True,
    )
    assert result.unified_slice_enabled is True
    assert result.info_message is None


@pytest.mark.parametrize("status", [_ABI_MISMATCH, _KAT_CORRUPT, _LOAD_ERROR])
def test_default_on_eligible_shape_with_broken_companion_fails_closed(status):
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="default",
            chunked=False,
            any_generate=False,
            config_dict=_eligible_config(),
            status=status,
        )
    assert exc_info.value.code == f"native_companion_{status.reason}"
    assert "cause" not in str(exc_info.value).lower()


def test_default_broken_companion_fails_closed_despite_unloaded_extra_source():
    """dennis re-verify MEDIUM-1, gate-level consequence: an extra declared
    source the loader never materializes must not scope the job OUT of the
    broken-companion fail-closed check (which would let it run on a broken
    install that admission would still have tried to use)."""
    config = _eligible_config()
    config["sources"]["archive"] = {"type": "s3", "bucket": "b", "key": "k.parquet"}
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="default",
            chunked=False,
            any_generate=False,
            config_dict=config,
            status=_KAT_CORRUPT,
        )
    assert exc_info.value.code == "native_companion_kat-corrupt"


def test_default_broken_companion_message_never_echoes_cause_object():
    """The message text is built from the classified `reason`, never the raw
    `status.cause` (which could chain a path-bearing exception)."""
    boom = _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI)
    with pytest.raises(NativeGateError) as exc_info:
        pre_execution_gate(
            intent="default",
            chunked=False,
            any_generate=False,
            config_dict=_eligible_config(),
            status=boom,
        )
    assert "kat-corrupt" in str(exc_info.value)


# ---------------------------------------------------------------------------
# post_run_verify -- Stage 2 (--native's post-run evidence check)
# ---------------------------------------------------------------------------


def _route(state):
    return classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics=(
            {"execution": {"execution_mode": "full_frame"}}
            if state == "pandas"
            else {
                "execution": {"execution_mode": "full_frame"},
                "unified_slice_activation": {
                    "activated": True,
                    "nodes": {
                        "n1": {
                            "operator": "native_keyed_hash",
                            "compiled_kernel_executed": state == "native",
                        }
                    },
                },
            }
        ),
    )


def test_post_run_verify_noop_for_default_intent():
    post_run_verify(intent="default", route=_route("pandas"))  # must not raise


def test_post_run_verify_noop_for_disable_intent():
    post_run_verify(intent="disable", route=_route("pandas"))  # must not raise


def test_post_run_verify_passes_require_intent_on_native_route():
    post_run_verify(intent="require", route=_route("native"))  # must not raise


@pytest.mark.parametrize("state", ["pandas", "unified_slice"])
def test_post_run_verify_fails_closed_require_intent_without_native_evidence(state):
    with pytest.raises(NativeGateError) as exc_info:
        post_run_verify(intent="require", route=_route(state))
    assert exc_info.value.code == "native_require_no_evidence"


def test_post_run_verify_fails_closed_on_non_applicable_route():
    non_candidate_route = classify_route(
        chunked=False,
        any_generate=False,
        resolved_substrate=None,
        quality_metrics={"execution": {"execution_mode": "sequential"}},
    )
    with pytest.raises(NativeGateError) as exc_info:
        post_run_verify(intent="require", route=non_candidate_route)
    assert exc_info.value.code == "native_require_no_evidence"
