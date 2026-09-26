"""End-to-end tests for `decoy run --native`/`--no-native` and the
native-route indicator (Phase 3.1: CLI native packaging default-on-when-present).

Two independent ways of driving each companion state, used side by side so
these tests hold regardless of whether a compiled `decoy-engine-native`
companion happens to be installed in whatever environment runs them:

1. **Genuine absence, everywhere, on demand.** `force_absent_companion`
   (a fixture below) sets `sys.modules["decoy_engine_native"] = None`,
   which is the standard way to make Python's import system report a
   module as genuinely not installed (`importlib.util.find_spec` returns
   `None` for a `None` sys.modules entry) -- this fools the ENGINE's own
   internal admission check too, not just the CLI-facing probe, because it
   acts at the import system itself rather than any one probe function.
   Confirmed directly: `run_pipeline` on an eligible hash/Parquet config
   produces `compiled_kernel_executed: true` with the fixture inactive (a
   real companion built via `maturin develop --release` in
   `decoy-engine/decoy-engine-native`) and produces no
   `unified_slice_activation` key at all with it active -- the exact
   state (c) contract. Tests that need `absent` for real use this fixture,
   not an assumption about the ambient environment.
2. **Genuine present-ok, when a companion is actually built.** Tests
   requiring compiled-kernel execution are guarded by
   `_NATIVE_COMPANION_INSTALLED` and skip (not fail) when no companion is
   importable -- true in CI today (no paired PyPI release exists yet, so
   nothing installs one there), false in this dev environment once one is
   built locally. Skipping is honest: the plan's whole premise is that the
   companion is optional, so a suite that hard-required one would
   contradict it.

Tests that need a BROKEN companion (abi-mismatch/kat-corrupt/load-error)
still monkeypatch `decoy_engine.native_companion_status` directly --
genuinely corrupting a loaded compiled extension is impractical, and this
only needs to control the CLI-side gate's OWN classification of an already
non-`ok` probe result, not the engine's admission decision (which the CLI
never disagrees with for a broken companion: both correctly avoid it).
"""

from __future__ import annotations

import importlib.util
import json as _json
import sys
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

_NATIVE_COMPANION_INSTALLED = importlib.util.find_spec("decoy_engine_native") is not None
_requires_real_companion = pytest.mark.skipif(
    not _NATIVE_COMPANION_INSTALLED,
    reason="needs a real compiled decoy-engine-native companion (none importable here)",
)


@pytest.fixture
def force_absent_companion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the companion genuinely absent for BOTH the CLI probe and the
    engine's own internal admission check, regardless of whether one is
    actually installed in this environment. See module docstring point 1."""
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


def test_run_falls_back_to_legacy_pandas_when_companion_absent(
    tmp_path: Path, force_absent_companion: None
):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["state"] == "pandas"
    assert payload["native_route"]["applicable"] is True
    assert (tmp_path / "out.csv").exists()


def test_run_absent_companion_prints_install_hint(tmp_path: Path, force_absent_companion: None):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert "decoy explain native" in result.output


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


def test_run_json_error_envelope_carries_native_error_kind_and_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M3 regression (dennis round 2): a NativeGateError's `code` must ride
    in the `--json` error envelope as `error_kind`/`code`, matching the
    existing `capacity_code` convention, so a script can branch on it
    without parsing message text."""
    _patch_status(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == EXIT_USAGE
    payload = _json.loads(result.stdout)
    assert payload["error_kind"] == "native"
    assert payload["code"] == "native_companion_kat-corrupt"


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


def test_broken_companion_does_not_affect_a_live_vault_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`vault_active` wiring (M1/L5 remediation, dennis round 2): a broken
    companion must not block a `--vault` run -- admission always declines a
    live vault writer regardless of companion health, so this job was never
    going to touch native either way. (A `vault: true` column also trips
    `static_native_eligibility`'s own config-shape check, which alone would
    already cover this observable outcome; `vault_active`'s unit-level
    behavior in isolation -- a config with NO `vault: true` column but a
    live writer anyway -- is covered by
    `test_default_on_eligible_shape_with_live_vault_writer_never_probes` in
    `tests/unit/test_native_gate.py`.)"""
    pytest.importorskip("cryptography")
    _patch_status(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    src = tmp_path / "in.parquet"
    pd.DataFrame({"id": ["a", "b"], "email": ["a@x.com", "b@x.com"]}).to_parquet(src, index=False)
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "parquet", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "n", "vault": True},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))
    vault_path = tmp_path / "vault.bin"
    result = runner.invoke(app, ["run", str(config_path), "--vault", str(vault_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").exists()
    assert vault_path.exists()


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


def test_native_require_refuses_absent_companion(tmp_path: Path, force_absent_companion: None):
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
# State (a) "native (compiled kernel)", GENUINE: an actual compiled
# companion, actually invoked, with `compiled_kernel_executed` evidence the
# engine itself produced -- not simulated. Skips (does not fail) when no
# companion is importable in this environment (see module docstring point
# 2): true in CI today, false here once `maturin develop --release` has
# been run in `decoy-engine/decoy-engine-native`.
# ---------------------------------------------------------------------------


@_requires_real_companion
def test_run_native_when_companion_present_ok(tmp_path: Path):
    """The plan's own acceptance-test name. A REAL compiled companion, a
    REAL eligible hash job, no flags: the compiled kernel actually runs."""
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"] == {
        "applicable": True,
        "state": "native",
        "label": "native (compiled kernel)",
    }
    assert (tmp_path / "out.csv").exists()


@_requires_real_companion
def test_native_require_succeeds_with_a_real_companion(tmp_path: Path):
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native", "--json"])
    assert result.exit_code == 0, result.output
    assert _json.loads(result.stdout)["native_route"]["state"] == "native"
    assert (tmp_path / "out.csv").exists()


@_requires_real_companion
def test_output_file_bytes_identical_native_vs_genuinely_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The plan's actual claim, proven with a REAL compiled kernel on one
    side and a REAL absent companion on the other -- not two runs of the
    same mocked route. The native run happens FIRST, while the companion is
    genuinely present; `sys.modules["decoy_engine_native"] = None` is only
    applied afterward, before the second (absent) invocation, so the two
    calls see genuinely different companion states within one test."""
    (tmp_path / "native").mkdir()
    (tmp_path / "absent").mkdir()
    config_native = _hash_eligible_config(tmp_path / "native")
    config_absent = _hash_eligible_config(tmp_path / "absent")

    result_native = runner.invoke(app, ["run", str(config_native), "--json"])
    assert result_native.exit_code == 0, result_native.output
    assert _json.loads(result_native.stdout)["native_route"]["state"] == "native"

    monkeypatch.setitem(sys.modules, "decoy_engine_native", None)
    result_absent = runner.invoke(app, ["run", str(config_absent), "--json"])
    assert result_absent.exit_code == 0, result_absent.output
    assert _json.loads(result_absent.stdout)["native_route"]["state"] == "pandas"

    bytes_native = (tmp_path / "native" / "out.csv").read_bytes()
    bytes_absent = (tmp_path / "absent" / "out.csv").read_bytes()
    assert bytes_native == bytes_absent


# ---------------------------------------------------------------------------
# State (a) "native (compiled kernel)" CLI PLUMBING, portable across every
# environment (no real companion required): monkeypatches
# `decoy_engine.run_pipeline` itself, calling the REAL implementation first
# (so masked values are genuinely computed) and only overriding
# `quality_metrics` to carry the shape a real native run produces. This
# covers dispatch/rendering/write-path wiring even where no compiled
# companion can be built (e.g. a CI runner with no Rust toolchain); the
# tests above are the genuine acceptance evidence, these are the portable
# regression net under them.
# ---------------------------------------------------------------------------


def _install_fake_native_run_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr("decoy_engine.run_pipeline", _fake)


def test_run_dispatches_native_route_when_engine_reports_compiled_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch_status(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    _install_fake_native_run_pipeline(monkeypatch)
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"] == {
        "applicable": True,
        "state": "native",
        "label": "native (compiled kernel)",
    }
    assert (tmp_path / "out.csv").exists()


def test_run_summary_card_shows_native_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_status(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    _install_fake_native_run_pipeline(monkeypatch)
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert "native (compiled kernel)" in result.output


def test_native_require_succeeds_when_engine_reports_compiled_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch_status(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    _install_fake_native_run_pipeline(monkeypatch)
    config = _hash_eligible_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--native", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["native_route"]["state"] == "native"
    assert (tmp_path / "out.csv").exists()


def test_output_file_bytes_identical_native_vs_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The plan's actual claim: for a fixed writer/format, the WRITTEN file
    is byte-identical whether the run reports state (a) native or state (c)
    pandas. Both invocations mask the SAME source with the SAME deterministic
    config, so the underlying values are identical either way; state (a)'s
    `ExecutionResult` here is built from that same real computation (see
    `_install_fake_native_run_pipeline`), so this is not a vacuous
    same-input-same-output comparison of two mocks -- it proves
    `_write_mask_outputs` is invariant to the route metadata, exactly the
    property the byte-parity requirement is about."""
    (tmp_path / "absent").mkdir()
    (tmp_path / "native").mkdir()
    config_absent = _hash_eligible_config(tmp_path / "absent")
    config_native = _hash_eligible_config(tmp_path / "native")

    result_absent = runner.invoke(app, ["run", str(config_absent)])
    assert result_absent.exit_code == 0, result_absent.output

    _patch_status(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    _install_fake_native_run_pipeline(monkeypatch)
    result_native = runner.invoke(app, ["run", str(config_native), "--json"])
    assert result_native.exit_code == 0, result_native.output
    assert _json.loads(result_native.stdout)["native_route"]["state"] == "native"

    bytes_absent = (tmp_path / "absent" / "out.csv").read_bytes()
    bytes_native = (tmp_path / "native" / "out.csv").read_bytes()
    assert bytes_absent == bytes_native


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
