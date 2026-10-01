"""`decoy preflight` native companion health + static eligibility (Phase 3.1).

Preflight never runs the job; it reports companion health (pass/warn) and a
STATIC, config-shape-only eligibility possibility, explicitly labeled as
such (not a guarantee of the resolved route at run time -- see
`decoy._native_gate.static_native_eligibility`'s docstring).
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from decoy_engine import NativeCompanionStatus
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

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
        cause=RuntimeError("SECRET_PATH_SENTINEL/should/never/be/printed"),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, status: NativeCompanionStatus) -> None:
    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: status)


def _eligible_config(tmp_path: Path) -> Path:
    src = tmp_path / "in.parquet"
    pd.DataFrame({"id": ["a", "b"], "email": ["a@x.com", "b@x.com"]}).to_parquet(src, index=False)
    cfg = {
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
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.dump(cfg))
    return path


def _ineligible_config(tmp_path: Path) -> Path:
    """A `vault: true` column -- fails the static eligibility predicate
    whatever the source format (CSV sources are eligible by declared format)."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": ["a", "b"], "email": ["a@x.com", "b@x.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns", "vault": True},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.dump(cfg))
    return path


def test_preflight_reports_health_and_eligible_shape_json(tmp_path: Path):
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_companion"]["status"] == "pass"
    assert payload["native_companion"]["message"]  # non-empty either way (absent or healthy)
    assert payload["native_eligibility"]["status"] == "pass"
    assert "possibility" in payload["native_eligibility"]["message"].lower()
    assert "eligible" in payload["native_eligibility"]["message"].lower()


def test_preflight_reports_ineligible_shape_json(tmp_path: Path):
    config = _ineligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "not eligible" in payload["native_eligibility"]["message"].lower()


def test_preflight_warns_on_broken_companion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    assert result.exit_code == 0, result.output  # a warning alone does not fail preflight
    payload = _json.loads(result.stdout)
    assert payload["native_companion"]["status"] == "warn"
    assert payload["native_companion"]["code"] == "kat-corrupt"


def test_preflight_fail_on_warning_escalates_broken_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from decoy.cli.exit_codes import EXIT_USAGE  # noqa: F401 (imported for readability)

    _patch(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--fail-on-warning"])
    assert result.exit_code != 0


def test_preflight_human_mode_always_shows_native_lines(tmp_path: Path):
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config)])
    assert result.exit_code == 0, result.output
    assert "native" in result.output.lower()


def test_preflight_never_leaks_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch(monkeypatch, _status("load-error", present=True, ok=False, abi_actual=_ABI))
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    assert "SECRET_PATH_SENTINEL" not in result.output


def test_preflight_abi_actual_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hostile = ("y" * 10_000) + "\x00"
    _patch(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual=hostile))
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    payload = _json.loads(result.stdout)
    message = payload["native_companion"]["message"]
    assert "\x00" not in message
    assert len(message) < 500  # bounded by the capped abi_actual, not the raw 10k string


def test_preflight_degrades_gracefully_on_an_older_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """H1 regression (dennis round 2): an engine predating
    `native_companion_status()` must not crash `decoy preflight`."""
    import decoy_engine

    monkeypatch.delattr(decoy_engine, "native_companion_status", raising=False)
    config = _eligible_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_companion"]["status"] == "pass"
    assert "newer engine" in payload["native_companion"]["message"].lower()
