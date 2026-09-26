"""`decoy info` native-companion reporting (Phase 3.1).

`decoy info` surfaces `native_companion_status()` (presence, reason,
`abi_expected`, a sanitized `abi_actual`, version) in both JSON and human
mode, without ever showing `status.cause` (which may chain a
path-bearing exception -- see `decoy._native_gate`'s module docstring).
"""

from __future__ import annotations

import json as _json
import sys

import pytest
from decoy_engine import NativeCompanionStatus
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

_ABI = "decoy-native-abi-2"


@pytest.fixture
def force_absent_companion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes the companion genuinely absent regardless of whether one
    happens to be built in this environment -- see
    `tests/e2e/test_run_native.py`'s module docstring."""
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
        cause=RuntimeError("SECRET_PATH_SENTINEL/should/never/be/printed"),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, status: NativeCompanionStatus) -> None:
    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: status)


def test_info_reports_absent_companion_json(force_absent_companion: None):
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    companion = payload["native_companion"]
    assert companion["present"] is False
    assert companion["ok"] is False
    assert companion["reason"] == "absent"


def test_info_reports_present_ok_companion_json(monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    companion = _json.loads(result.stdout)["native_companion"]
    assert companion == {
        "present": True,
        "ok": True,
        "reason": "present-ok",
        "abi_expected": _ABI,
        "abi_actual": _ABI,
        "version": "9.9.9",
    }


def test_info_reports_broken_companion_json(monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual="v1"))
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    companion = _json.loads(result.stdout)["native_companion"]
    assert companion["ok"] is False
    assert companion["reason"] == "abi-mismatch"
    assert companion["abi_actual"] == "v1"


def test_info_never_leaks_cause(monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("load-error", present=True, ok=False, abi_actual=_ABI))
    result = runner.invoke(app, ["info", "--json"])
    assert "SECRET_PATH_SENTINEL" not in result.output
    assert "cause" not in _json.loads(result.stdout)["native_companion"]


def test_info_human_mode_shows_companion_status(monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "kat-corrupt" in result.output
    assert "SECRET_PATH_SENTINEL" not in result.output


def test_info_abi_actual_is_sanitized_before_display(monkeypatch: pytest.MonkeyPatch):
    hostile = ("x" * 10_000) + "\x00\x01"
    _patch(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual=hostile))
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    abi_actual = _json.loads(result.stdout)["native_companion"]["abi_actual"]
    assert len(abi_actual) <= 200
    assert "\x00" not in abi_actual
    assert "\x01" not in abi_actual


def test_info_version_is_sanitized_before_display(monkeypatch: pytest.MonkeyPatch):
    """L1 regression (dennis round 2): `version` is untrusted distribution
    metadata too (`importlib.metadata.version` on a hostile/malformed
    installed distribution), not just `abi_actual`."""
    hostile_version = ("v" * 10_000) + "\x00"
    status = NativeCompanionStatus(
        present=True,
        ok=True,
        abi_expected=_ABI,
        abi_actual=_ABI,
        version=hostile_version,
        reason="present-ok",
        cause=None,
    )
    _patch(monkeypatch, status)
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    version = _json.loads(result.stdout)["native_companion"]["version"]
    assert len(version) <= 200
    assert "\x00" not in version


def test_info_degrades_gracefully_on_an_older_engine(monkeypatch: pytest.MonkeyPatch):
    """H1 regression (dennis round 2): an engine predating
    `native_companion_status()` must not crash `decoy info` -- capability-
    detect and report `native_companion: null` instead."""
    import decoy_engine

    monkeypatch.delattr(decoy_engine, "native_companion_status", raising=False)
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0, result.output
    assert _json.loads(result.stdout)["native_companion"] is None


def test_info_human_mode_degrades_gracefully_on_an_older_engine(monkeypatch: pytest.MonkeyPatch):
    import decoy_engine

    monkeypatch.delattr(decoy_engine, "native_companion_status", raising=False)
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.output
    assert "not checked" in result.output.lower()
