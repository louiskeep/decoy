"""End-to-end tests for `decoy run --native`/`--no-native` and the
native-route indicator (Phase 3.1: CLI native packaging default-on-when-present).

This dev/test environment has no compiled `decoy-engine-native` companion
installed (no paired PyPI release exists yet -- see the plan's packaging
section), so `native_companion_status()` genuinely reports `absent` here.
Tests that need `present-ok` or a broken companion monkeypatch
`decoy_engine.native_companion_status` -- the exact spot both
`decoy._native_gate` and `decoy.cli.info`/`decoy.cli.preflight` read it from.
That monkeypatch controls the CLI-side gate's OWN decision (Stage 0/1, the
info/warn text, `decoy info`/`decoy preflight` reporting) fully; it does NOT
make the engine's internal admission predicate see a healthy companion (that
reads the probe from a different import path, by design -- see
`decoy_engine/execution/physical/_snapshot.py` /`_live_inputs.py`), so a
"required a compiled kernel" run in this environment always finishes via the
legacy pandas route regardless of what the CLI gate believed going in. State
(a) "native (compiled kernel)" is covered at the unit level instead
(`tests/unit/test_native_gate.py::test_classify_route_activation_with_compiled_kernel_is_native`),
reading a synthetic `ExecutionResult.quality_metrics` shaped exactly like a
real native run would produce -- the engine's own D9 cert already proves a
real compiled kernel produces that shape (out of this CLI plan's scope).
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
from decoy.cli.exit_codes import EXIT_USAGE

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


def _patch_status(monkeypatch: pytest.MonkeyPatch, status: NativeCompanionStatus) -> None:
    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: status)


def _write_parquet(path: Path, rows: int = 20) -> None:
    pd.DataFrame(
        {
            "id": [f"C{i}" for i in range(rows)],
            "email": [f"user{i}@example.com" for i in range(rows)],
        }
    ).to_parquet(path, index=False)


def _hash_eligible_config(tmp_path: Path, *, source_name: str = "in.parquet") -> Path:
    """Single non-FK table, Parquet source, passthrough + hash columns --
    the static-eligibility shape (would reach the companion-health gate)."""
    src = tmp_path / source_name
    _write_parquet(src)
    config = {
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
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


def _non_hash_parquet_config(tmp_path: Path) -> Path:
    """Same shape, but no hash column: eligible for the unified slice without
    ever needing the companion (state b)."""
    src = tmp_path / "in.parquet"
    _write_parquet(src)
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "parquet", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "redact"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


def _csv_hash_config(tmp_path: Path) -> Path:
    """A hash job over a CSV source: not static-eligible (non-Parquet), but
    still a coarse unified-slice CANDIDATE (non-chunked, mask-only)."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": ["a", "b", "c"], "email": ["a@x.com", "b@x.com", "c@x.com"]}).to_csv(
        src, index=False
    )
    config = {
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
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


def _generate_only_config(tmp_path: Path) -> Path:
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {},
        "tables": [
            {
                "name": "employees",
                "row_count": 3,
                "generate_columns": [
                    {"name": "employee_id", "type": "sequence", "start": 1, "step": 1},
                ],
            },
        ],
        "targets": {
            "employees": {"type": "file", "format": "csv", "path": str(tmp_path / "gen.csv")}
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


# ---------------------------------------------------------------------------
# Help / flag plumbing
# ---------------------------------------------------------------------------


def test_run_help_shows_native_flags():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--native" in result.stdout
    assert "--no-native" in result.stdout


def test_native_and_no_native_are_mutually_exclusive(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native", "--no-native"])
    assert result.exit_code == EXIT_USAGE
    assert "mutually exclusive" in result.output


# ---------------------------------------------------------------------------
# Present/absent/broken matrix -- no flag (default intent)
# ---------------------------------------------------------------------------


def test_run_falls_back_to_legacy_pandas_when_companion_absent(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["state"] == "pandas"
    assert payload["native_route"]["applicable"] is True
    assert (tmp_path / "out.csv").exists()


def test_run_absent_companion_prints_install_hint(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert "decoy-cli[native]" in result.output


def test_nonhash_job_reports_unified_slice_without_companion(tmp_path: Path):
    config = _non_hash_parquet_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["state"] == "unified_slice"
    assert "pandas" not in payload["native_route"]["label"]


def test_run_fails_closed_on_broken_companion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_status(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE
    assert "kat-corrupt" in result.output
    assert "SECRET_PATH_SENTINEL" not in result.output
    assert not (tmp_path / "out.csv").exists()


@pytest.mark.parametrize("reason", ["abi-mismatch", "kat-corrupt", "load-error"])
def test_run_fails_closed_on_every_broken_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
):
    _patch_status(monkeypatch, _status(reason, present=True, ok=False, abi_actual=_ABI))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE
    assert reason in result.output
    assert not (tmp_path / "out.csv").exists()


def test_broken_companion_does_not_affect_non_eligible_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A broken companion must not block a job that was never going to touch
    native (no hash column) -- the default-intent fail-closed check is
    scoped to static eligibility."""
    _patch_status(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _non_hash_parquet_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").exists()


# ---------------------------------------------------------------------------
# --no-native
# ---------------------------------------------------------------------------


def test_no_native_flag_forces_legacy_pandas(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--no-native", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["state"] == "pandas"


def test_no_native_downgrades_broken_companion_to_warned_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch_status(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--no-native"])
    assert result.exit_code == 0, result.output
    assert "kat-corrupt" in result.output
    assert (tmp_path / "out.csv").exists()


# ---------------------------------------------------------------------------
# --native (require)
# ---------------------------------------------------------------------------


def test_native_require_refuses_absent_companion(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native"])
    assert result.exit_code == EXIT_USAGE
    assert "absent" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_native_require_refuses_broken_companion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_status(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual="v1"))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native"])
    assert result.exit_code == EXIT_USAGE
    assert "abi-mismatch" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_native_chunked_rejected_before_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _boom(*args, **kwargs):
        raise AssertionError("run_mask_pipeline_chunked must not be called")

    monkeypatch.setattr("decoy_engine.run_mask_pipeline_chunked", _boom)
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native", "--chunked"])
    assert result.exit_code == EXIT_USAGE
    assert "chunked" in result.output.lower() or "unified slice" in result.output.lower()
    assert not (tmp_path / "out.csv").exists()


def test_native_on_generate_only_rejected_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def _boom(*args, **kwargs):
        raise AssertionError("run_pipeline must not be called")

    monkeypatch.setattr("decoy_engine.run_pipeline", _boom)
    config = _generate_only_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native"])
    assert result.exit_code == EXIT_USAGE
    assert not (tmp_path / "gen.csv").exists()


def test_native_require_fails_closed_on_runtime_ineligible_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """--native with a HEALTHY (per the CLI gate) companion on a candidate
    that turns out runtime-ineligible (a non-Parquet source here) runs, then
    fails closed post-run with no compiled-kernel evidence -- no output
    written. Stage 1 is satisfied by monkeypatching the CLI-side probe to
    present-ok; the real (absent) companion this dev environment has makes
    the engine's own admission decline independently, landing on the same
    "no compiled-kernel evidence" outcome Stage 2 must catch regardless of
    which reason produced it."""
    _patch_status(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    config = _csv_hash_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native"])
    assert result.exit_code == EXIT_USAGE
    assert not (tmp_path / "out.csv").exists()


# ---------------------------------------------------------------------------
# Route indicator: non-candidate shapes
# ---------------------------------------------------------------------------


def test_route_indicator_not_applicable_for_generate_only(tmp_path: Path):
    config = _generate_only_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["applicable"] is False
    assert payload["native_route"]["state"] is None


def test_route_indicator_reports_resolved_substrate_for_chunked(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--chunked", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["applicable"] is False
    assert payload["native_route"]["label"] == "pandas chunked stream"


# ---------------------------------------------------------------------------
# Output-file-byte parity (CLI's own contract, distinct from the engine's
# cell/schema D9 cert)
# ---------------------------------------------------------------------------


def test_output_file_bytes_identical_default_vs_no_native(tmp_path: Path):
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    config_a = _hash_eligible_config(tmp_path / "a")
    config_b = _hash_eligible_config(tmp_path / "b")

    result_a = runner.invoke(app, ["run", str(config_a)])
    assert result_a.exit_code == 0, result_a.output
    result_b = runner.invoke(app, ["run", str(config_b), "--no-native"])
    assert result_b.exit_code == 0, result_b.output

    bytes_a = (tmp_path / "a" / "out.csv").read_bytes()
    bytes_b = (tmp_path / "b" / "out.csv").read_bytes()
    assert bytes_a == bytes_b


def test_output_file_bytes_identical_nonhash_default_vs_no_native(tmp_path: Path):
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    config_a = _non_hash_parquet_config(tmp_path / "a")
    config_b = _non_hash_parquet_config(tmp_path / "b")

    result_a = runner.invoke(app, ["run", str(config_a)])
    assert result_a.exit_code == 0, result_a.output
    result_b = runner.invoke(app, ["run", str(config_b), "--no-native"])
    assert result_b.exit_code == 0, result_b.output

    bytes_a = (tmp_path / "a" / "out.csv").read_bytes()
    bytes_b = (tmp_path / "b" / "out.csv").read_bytes()
    assert bytes_a == bytes_b


# ---------------------------------------------------------------------------
# Privacy: never leak status.cause / source values
# ---------------------------------------------------------------------------


def test_broken_companion_error_never_leaks_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_status(monkeypatch, _status("load-error", present=True, ok=False, abi_actual=_ABI))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert "SECRET_PATH_SENTINEL" not in result.output
