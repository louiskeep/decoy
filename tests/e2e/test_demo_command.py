"""End-to-end tests for `decoy demo`.

CLI.3 commit 3 (2026-06-02): rewritten against the V2 demo body.
Pre-rewrite the file exercised the V1 demo flow (scan -> FORECAST ->
hash-based mask via the deleted Masker class) + the --ref multi-table
FK-via-hash flow. Both are dead under storm-reframe-C and S22-CL-
V1GRAPHRUNNER. The new cells verify (a) help text renders, (b) the
single-table demo runs end-to-end and produces customers_masked.csv,
(c) the --ref flow exits 1 with the deferral message pointing at the
single-table demo as the workaround.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


# --------------------------------------------------------------------------
# Help text
# --------------------------------------------------------------------------


def test_demo_help_includes_examples():
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_demo_help_documents_ref_flag():
    """--ref flag stays on the surface even though the body is deferred,
    so a user who tries it gets the typed deferral message instead of
    'unknown flag'."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "--ref" in result.stdout
    assert "--rows" in result.stdout


# --------------------------------------------------------------------------
# Single-table flow (V2 spine)
# --------------------------------------------------------------------------


def test_demo_runs_end_to_end(tmp_path: Path):
    """The new single-table demo: write customers.csv -> STORM scan ->
    V2 mask -> customers_masked.csv. The FORECAST step is dropped (no
    V2 successor); the sample CSV name changed from patients to
    customers to match the V2 demo body."""
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir)])
    assert result.exit_code == 0, result.output

    assert (out_dir / "customers.csv").exists()
    assert (out_dir / "customers_masked.csv").exists()
    assert (out_dir / "scan.json").exists()
    assert (out_dir / "pipeline.yaml").exists()
    # FORECAST step deleted under storm-reframe-C; no forecast.json.
    assert not (out_dir / "forecast.json").exists()

    masked = (out_dir / "customers_masked.csv").read_text()
    # PII columns are either faker-replaced or redacted.
    assert "alice@example.com" not in masked
    assert "111-22-3333" not in masked
    assert "REDACTED" in masked


def test_demo_json_envelope(tmp_path: Path):
    """JSON envelope shape: V2 demo carries `pii_columns` but no
    `top_disguise` (FORECAST step deleted)."""
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "demo"
    assert payload["variant"] == "single"
    assert payload["status"] == "ok"
    assert payload["pii_columns"] >= 3
    assert "top_disguise" not in payload


def test_demo_quiet_produces_empty_stdout(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert (out_dir / "customers_masked.csv").exists()


def test_demo_writes_masked_csv_with_same_row_count_as_sample(tmp_path: Path):
    """Sample CSV is 10 rows (constant; see demo._write_sample_csv).
    Masked output preserves the row count."""
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    source = pd.read_csv(out_dir / "customers.csv")
    masked = pd.read_csv(out_dir / "customers_masked.csv")
    assert len(masked) == len(source)


def test_demo_masked_pipeline_yaml_is_v2_shape(tmp_path: Path):
    """The pipeline.yaml the demo writes is a valid V2 PipelineConfig:
    version: 1, sources/tables/targets blocks. FC-1 (2026-06-02): the
    top-level `mode:` field is gone; per-table kind is inferred from
    `columns` vs `generate_columns` presence. The demo's single table
    declares `columns`, making it mask-kind."""
    import yaml as _yaml

    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    cfg = _yaml.safe_load((out_dir / "pipeline.yaml").read_text(encoding="utf-8"))
    assert cfg.get("version") == 1
    assert "sources" in cfg
    assert "tables" in cfg
    assert "targets" in cfg
    # Per-table kind: demo's single table is mask-kind.
    assert all(t.get("columns") for t in cfg["tables"])


def test_demo_with_relative_out_dir_does_not_double_resolve(tmp_path: Path):
    """Dennis launch-readiness audit (2026-06-02) BLOCKER regression pin.

    Pre-fix: `decoy demo --dir decoy_demo` left `out_dir` as a relative
    Path. `_build_pipeline_yaml` wrote `decoy_demo/customers.csv` into
    the YAML; `_run_v2_mask` then re-resolved that against
    `pipeline_yaml.parent` (which is `decoy_demo` again), producing
    `decoy_demo/decoy_demo/customers.csv` and crashing with
    FileNotFoundError. The README quickstart is `pip install decoy &&
    decoy demo`; this bug would have killed every first-run experience.

    Fix: `demo` resolves `out_dir` to absolute up front so all derived
    paths in the YAML are absolute too. This test invokes the demo with
    a relative `--dir` from a working directory we control via chdir,
    then asserts the masked output file actually exists at the
    declared path."""
    import os

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Invoke with a RELATIVE --dir (the default invocation shape).
        result = runner.invoke(app, ["demo", "--dir", "demo_out", "--quiet"])
        assert result.exit_code == 0, result.stdout + result.stderr
        # Expected output file at the relative-to-cwd path. If the
        # double-resolve regression returns, this path is empty and the
        # actual file is at demo_out/demo_out/customers_masked.csv.
        masked = tmp_path / "demo_out" / "customers_masked.csv"
        assert masked.exists() and masked.stat().st_size > 0, (
            f"masked output missing at {masked}; the double-resolve "
            f"regression may have returned"
        )
        # And the WRONG path must NOT exist.
        wrong = tmp_path / "demo_out" / "demo_out" / "customers_masked.csv"
        assert not wrong.exists(), (
            f"masked output landed at the double-resolved path "
            f"{wrong}; demo is re-resolving relative paths twice"
        )
    finally:
        os.chdir(cwd)


# --------------------------------------------------------------------------
# --ref deferral (Q-CLI3-1 Dennis resolution: drop > 0.5d effort)
# --------------------------------------------------------------------------


def test_demo_ref_exits_with_deferral_message(tmp_path: Path):
    """CLI.3 commit 2 (2026-06-02): --ref is deferred to a follow-up
    sprint. Pre-rewrite the flow built three V1-shape YAMLs and ran
    `Masker(...).mask()` to test FK preservation via a shared truncated
    hash. The V2 equivalent needs a single multi-table PipelineConfig
    with a relationships: block; out of CLI.3 scope per Q-CLI3-1."""
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 1
    assert "deferred" in result.output.lower()


def test_demo_ref_json_envelope_carries_typed_error(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50", "--json"]
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "demo"
    assert payload["variant"] == "ref"
    assert payload["status"] == "error"
    assert "deferred" in payload["error"].lower()
    assert "decoy demo" in payload["error"]


def test_demo_ref_does_not_create_output_files(tmp_path: Path):
    """The deferral message is the only side effect; no V1-shape YAML
    or masked CSV is written."""
    out_dir = tmp_path / "demo_ref"
    runner.invoke(app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"])
    # The directory may exist (created by the entrypoint) but should be
    # empty of demo artifacts.
    if out_dir.exists():
        contents = list(out_dir.iterdir())
        # Allow empty directory; reject if it carries demo CSVs.
        bad = [p for p in contents if p.suffix == ".csv" or p.suffix == ".yaml"]
        assert not bad, f"--ref deferral should not write demo artifacts; got {bad}"
