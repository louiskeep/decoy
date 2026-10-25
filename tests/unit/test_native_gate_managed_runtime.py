"""Native-on-by-default, loud refusal under a managed runtime (B-2, item 4).

A managed bundle ships the matched native companion by construction, so under the
managed-runtime marker a missing companion on a native-eligible job is a loud
refusal, never a silent drop to the slow pandas path. A present-but-broken
(mismatched) companion already refuses regardless of the marker; a bare `pip`
install (no marker) keeps today's soft info-and-fallback on an absent companion.

The gate takes an injected `status`, so these run with no engine installed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from decoy import _native_gate
from decoy._native_gate import NativeGateError, pre_execution_gate

# A single-table, single-hash-column, csv-file config: native-eligible, so the
# default-intent path reaches the companion probe (static_native_eligibility is
# True). See decoy._native_gate.static_native_eligibility.
_ELIGIBLE_CONFIG = {
    "tables": [{"name": "t", "columns": [{"name": "c", "strategy": "hash"}]}],
    "sources": {"t": {"type": "file", "format": "csv", "path": "t.csv"}},
}


def _status(*, present: bool, ok: bool, reason: str):
    return SimpleNamespace(
        present=present,
        ok=ok,
        reason=reason,
        abi_expected="decoy-native-abi-2",
        abi_actual=None,
        version=None,
    )


def _gate(**kw):
    base = dict(
        intent="default",
        chunked=False,
        any_generate=False,
        config_dict=_ELIGIBLE_CONFIG,
    )
    base.update(kw)
    return pre_execution_gate(**base)


def test_managed_runtime_absent_companion_is_a_loud_refusal():
    with pytest.raises(NativeGateError) as exc:
        _gate(managed_runtime=True, status=_status(present=False, ok=False, reason="absent"))
    assert exc.value.code == "native_managed_absent"
    assert "managed Decoy runtime" in str(exc.value)


def test_unmanaged_absent_companion_stays_soft_fallback():
    result = _gate(managed_runtime=False, status=_status(present=False, ok=False, reason="absent"))
    assert result.unified_slice_enabled is True
    assert result.info_message is not None
    assert "Python fallback" in result.info_message


def test_managed_runtime_broken_companion_refuses():
    # Present-but-broken already refuses; the managed marker does not change that
    # (the message is the present-but-broken classification, not the managed one).
    with pytest.raises(NativeGateError) as exc:
        _gate(managed_runtime=True, status=_status(present=True, ok=False, reason="abi-mismatch"))
    assert exc.value.code == "native_companion_abi-mismatch"


def test_unmanaged_broken_companion_still_refuses():
    with pytest.raises(NativeGateError) as exc:
        _gate(managed_runtime=False, status=_status(present=True, ok=False, reason="abi-mismatch"))
    assert exc.value.code == "native_companion_abi-mismatch"


def test_managed_runtime_healthy_companion_runs():
    result = _gate(managed_runtime=True, status=_status(present=True, ok=True, reason="ok"))
    assert result.unified_slice_enabled is True


def test_managed_runtime_detected_from_env(monkeypatch):
    monkeypatch.setenv(_native_gate.MANAGED_RUNTIME_ENV, "1")
    with pytest.raises(NativeGateError) as exc:
        # managed_runtime omitted: detected from the environment marker.
        _gate(status=_status(present=False, ok=False, reason="absent"))
    assert exc.value.code == "native_managed_absent"


def test_env_marker_off_values_are_not_managed(monkeypatch):
    for off in ("", "0", "false", "False"):
        monkeypatch.setenv(_native_gate.MANAGED_RUNTIME_ENV, off)
        result = _gate(status=_status(present=False, ok=False, reason="absent"))
        assert result.unified_slice_enabled is True
        assert result.info_message is not None


def test_managed_runtime_ineligible_job_is_not_refused():
    # A generate job is not a unified-slice candidate, so native-on does not
    # apply and a missing companion is not a slow-path risk: no refusal even
    # under the managed marker.
    result = _gate(
        any_generate=True,
        managed_runtime=True,
        status=_status(present=False, ok=False, reason="absent"),
    )
    assert result.unified_slice_enabled is True
