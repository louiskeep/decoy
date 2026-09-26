"""`decoy.mask(native=...)` (Phase 3.1): the library mirrors `decoy run`'s
`--native`/`--no-native` through the SAME shared gate
(`decoy._native_gate`), so it cannot silently write an ineligible-shape
result the CLI would refuse.

See `tests/e2e/test_run_native.py`'s module docstring for the two ways
these tests drive a companion state portably (a `force_absent_companion`
fixture using `sys.modules["decoy_engine_native"] = None`, which fools the
engine's own admission check too, not just the library-facing probe; and a
`_requires_real_companion` skip guard for tests needing GENUINE
compiled-kernel execution, true only when one has actually been built
locally -- e.g. `maturin develop --release` in
`decoy-engine/decoy-engine-native`).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
from decoy_engine import NativeCompanionStatus

import decoy
from decoy._native_gate import NativeGateError

_ABI = "decoy-native-abi-2"

_NATIVE_COMPANION_INSTALLED = importlib.util.find_spec("decoy_engine_native") is not None
_requires_real_companion = pytest.mark.skipif(
    not _NATIVE_COMPANION_INSTALLED,
    reason="needs a real compiled decoy-engine-native companion (none importable here)",
)


@pytest.fixture
def force_absent_companion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "decoy_engine_native", None)


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


def _patch(monkeypatch: pytest.MonkeyPatch, status: NativeCompanionStatus) -> None:
    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: status)


@pytest.fixture
def eligible_parquet_config(tmp_path: Path) -> dict:
    src = tmp_path / "in.parquet"
    pd.DataFrame({"id": ["a", "b", "c"], "email": ["a@x.com", "b@x.com", "c@x.com"]}).to_parquet(
        src, index=False
    )
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "parquet", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }


@pytest.fixture
def csv_config(tmp_path: Path) -> dict:
    """Non-Parquet source: coarse candidate, not static-eligible."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": ["a", "b"], "email": ["a@x.com", "b@x.com"]}).to_csv(src, index=False)
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }


def test_mask_default_native_falls_back_silently(
    eligible_parquet_config: dict, tmp_path: Path, force_absent_companion: None
):
    """M4 regression (dennis round 2): the ordinary absent-companion case
    must NEVER raise/emit a `UserWarning` -- a caller running with
    warnings-as-errors would otherwise get an exception from a normal
    `mask()` call. `pytest.warns` isn't used here (it expects at least one
    matching warning); `recwarn` asserts none fired instead."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = decoy.mask(config=eligible_parquet_config)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_native_true_uses_shared_gate_absent_companion(
    eligible_parquet_config: dict, tmp_path: Path, force_absent_companion: None
):
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=eligible_parquet_config, native=True)
    assert exc_info.value.code.startswith("native_require_")
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_refuses_broken_companion(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    with pytest.raises(NativeGateError):
        decoy.mask(config=eligible_parquet_config, native=True)
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_false_forces_legacy_pandas(eligible_parquet_config: dict, tmp_path: Path):
    out = decoy.mask(config=eligible_parquet_config, native=False)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_default_broken_companion_fails_closed_no_return(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mirrors `decoy run`'s default-intent fail-closed-on-broken-companion
    behavior: `mask()` returns no DataFrame and writes no output."""
    _patch(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual="v1"))
    with pytest.raises(NativeGateError):
        decoy.mask(config=eligible_parquet_config)
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_fails_closed_on_runtime_ineligible_candidate(
    csv_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Stage 1 passes (companion reported healthy); the job runs, then fails
    closed post-run with no compiled-kernel evidence -- returns no
    DataFrame, writes no output, the SAME outcome `decoy run --native`
    gives for the same shape (P1-3)."""
    _patch(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=csv_config, native=True)
    assert exc_info.value.code == "native_require_no_evidence"
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_on_generate_only_rejected_before_dispatch(tmp_path: Path):
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "tables": [
            {
                "name": "employees",
                "row_count": 3,
                "generate_columns": [{"name": "id", "type": "sequence", "start": 1, "step": 1}],
            }
        ],
        "targets": {
            "employees": {"type": "file", "format": "csv", "path": str(tmp_path / "gen.csv")}
        },
    }
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=config, native=True)
    assert exc_info.value.code == "native_require_not_a_candidate"
    assert not (tmp_path / "gen.csv").exists()


@_requires_real_companion
def test_mask_native_true_succeeds_with_a_real_companion(
    eligible_parquet_config: dict, tmp_path: Path
):
    """Genuine acceptance evidence (skips, does not fail, when no compiled
    companion is importable here): `mask(native=True)` against a REAL
    companion actually returns a DataFrame and writes the file, using a
    genuinely executed compiled kernel."""
    out = decoy.mask(config=eligible_parquet_config, native=True)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_dispatches_native_route_when_engine_reports_compiled_kernel(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """State (a) at the library dispatch level (portable plumbing check that
    runs regardless of environment; see the genuine-companion test above for
    the real acceptance evidence). The fake `run_pipeline` wrapper calls the
    REAL one first (genuinely computed masked values) and only overrides
    `quality_metrics` to carry the shape a real native run would produce --
    proving `mask(native=True)` actually returns/writes on a native outcome,
    not just that the shared gate classifies one correctly in isolation."""
    import decoy_engine
    from decoy_engine import ExecutionResult

    real_run_pipeline = decoy_engine.run_pipeline

    def _fake(*args, **kwargs):
        result = real_run_pipeline(*args, **kwargs)
        native_metrics = dict(result.quality_metrics)
        native_metrics["unified_slice_activation"] = {
            "activated": True,
            "table": "customers",
            "nodes": {
                "n1": {
                    "operator": "native_keyed_hash",
                    "executed": True,
                    "compiled_kernel_executed": True,
                }
            },
        }
        return ExecutionResult(
            outputs=result.outputs,
            timings=result.timings,
            boundary_conversion_ms=result.boundary_conversion_ms,
            warnings=result.warnings,
            quality_metrics=native_metrics,
            table_kinds=result.table_kinds,
            row_errors=result.row_errors,
        )

    _patch(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    monkeypatch.setattr("decoy_engine.run_pipeline", _fake)

    out = decoy.mask(config=eligible_parquet_config, native=True)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_default_and_native_true_stay_compatible_with_an_older_engine(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """H1 regression (Codex round-2 repro): `mask()` must never pass
    `unified_slice_enabled=True` explicitly -- an engine whose `run_pipeline`
    predates that kwarg entirely would raise `TypeError` on every plain
    call, not just a `--no-native` one. Simulates that older engine by
    wrapping the real `run_pipeline` and asserting the kwarg never arrives
    unless it is `False`."""
    import decoy_engine

    real_run_pipeline = decoy_engine.run_pipeline

    def _old_engine_run_pipeline(*args, **kwargs):
        if "unified_slice_enabled" in kwargs and kwargs["unified_slice_enabled"] is not False:
            raise TypeError(
                "old_run_pipeline() got an unexpected keyword argument 'unified_slice_enabled'"
            )
        kwargs.pop("unified_slice_enabled", None)
        return real_run_pipeline(*args, **kwargs)

    monkeypatch.setattr("decoy_engine.run_pipeline", _old_engine_run_pipeline)

    # Default intent: must not pass the kwarg at all.
    out = decoy.mask(config=eligible_parquet_config)
    assert isinstance(out, pd.DataFrame)

    # native=True with a companion the CLI-side gate believes is healthy:
    # Stage 1 passes, so this actually REACHES the old-engine fake. Forcing
    # the companion genuinely absent (regardless of whether one happens to
    # be built in this environment) makes admission decline the hash gate,
    # so Stage 2 refuses for lack of compiled-kernel evidence -- but that
    # must be `post_run_verify`'s NativeGateError, not a TypeError from
    # `unified_slice_enabled=True` hitting the simulated old engine.
    _patch(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    monkeypatch.setitem(sys.modules, "decoy_engine_native", None)
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=eligible_parquet_config, native=True)
    assert exc_info.value.code == "native_require_no_evidence"
