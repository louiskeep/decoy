"""End-to-end tests for `decoy init`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def test_init_help_includes_examples():
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_init_quiet_writes_minimal_pipeline(tmp_path: Path):
    """CLI.3 (2026-06-02): bundled minimal template is now V2 PipelineConfig
    shape: `version: 1`, `tables[].columns`, no `masking_rules`."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", "--out", str(out), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert data.get("version") == 1
    assert "tables" in data
    assert len(data["tables"]) >= 1
    assert len(data["tables"][0]["columns"]) >= 3


def test_init_json_returns_metadata(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", "--out", str(out), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "init"
    assert payload["status"] == "ok"
    assert payload["preset"] == "minimal"
    assert payload["rule_count"] >= 3


def test_init_refuses_to_overwrite_in_json_mode(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    out.write_text("existing")
    result = runner.invoke(app, ["init", "--out", str(out), "--json"])
    assert result.exit_code == 1
    assert "already exists" in result.stderr


def test_init_overwrites_with_yes_flag(tmp_path: Path):
    """CLI.3 (2026-06-02): bundled template body is V2 (`tables:` block)."""
    out = tmp_path / "pipeline.yaml"
    out.write_text("existing")
    result = runner.invoke(app, ["init", "--out", str(out), "--yes", "--quiet"])
    assert result.exit_code == 0
    assert "tables:" in out.read_text()


def test_init_preset_hipaa_writes_hipaa_template(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "hipaa", "--out", str(out), "--quiet"]
    )
    assert result.exit_code == 0
    body = out.read_text()
    # Pulled from the bundled hipaa template -- must include PHI columns.
    assert "first_name" in body
    assert "mrn" in body
    assert "ssn" in body


def test_init_preset_unknown_suggests_close_match(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app,
        ["init", "--preset", "hippa", "--out", str(out), "--yes"],
    )
    assert result.exit_code == 1
    assert "unknown preset" in result.stderr.lower()
    assert "hipaa" in result.stderr


def test_init_preset_json_envelope_carries_preset_and_count(tmp_path: Path):
    import json as _json

    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "pci", "--out", str(out), "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["preset"] == "pci"
    assert payload["rule_count"] >= 1


def test_init_preset_generate_produces_generator_yaml(tmp_path: Path):
    """The generate preset uses `mode: generate` + `generate_columns`. CLI.3
    (2026-06-02): V1 `generator_settings:` block folded into the unified
    V2 `global_settings:`."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "generate", "--out", str(out), "--quiet"]
    )
    assert result.exit_code == 0
    body = out.read_text()
    assert "tables:" in body
    assert "mode: generate" in body
    assert "generate_columns:" in body


# --- Regression: column-aware scaffold must round-trip through the real ---
# --- engine ColumnConfig (extra="forbid"), not just the CLI's own       ---
# --- best-effort `_validate_scaffold` check (which silently no-ops if   ---
# --- decoy_engine can't be imported). This is the gap that let a       ---
# --- `params:` block ship for date_shift/truncate/fpe: no test drove   ---
# --- `decoy init <file>` on data that infers to those three strategies ---
# --- and then independently re-validated the output against            ---
# --- `decoy_engine.config.PipelineConfig` (extra="forbid" has no       ---
# --- `params` field on ColumnConfig -- decoy_engine/src/decoy_engine/  ---
# --- config/_tables.py).                                                ---
#
# Two-model-gate follow-up (2026-07-15): `PipelineConfig.model_validate`
# passing is a WEAKER property than the scaffold actually being runnable --
# hash/fpe/date_shift also require a `namespace:` at RUNTIME (execution/
# _strategies/_hash.py, _fpe.py, _date_shift.py raise `<strategy>_requires_
# namespace`), which model_validate does not check (ColumnConfig.namespace
# defaults to None with no compile-time guard). The round-trip test below
# now drives a REAL `decoy run` end to end (not just model_validate) so a
# regression that reintroduces a missing-namespace scaffold fails loudly
# instead of silently passing schema validation and only breaking at
# `decoy run` in the user's hands.


def _luhn_valid(number: str) -> bool:
    """Minimal Luhn checksum, independent of the engine's own implementation
    (`decoy_engine.transforms.fpe`), so this test proves the masked PAN is
    Luhn-valid rather than re-testing the engine's own check against itself."""
    digits = [int(c) for c in number if c.isdigit()]
    if not digits:
        return False
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@pytest.fixture
def csv_with_date_zip_pan_id(tmp_path: Path) -> Path:
    """Columns that STORM should infer to date_shift, truncate, fpe, and
    hash respectively (per `_INFERENCE_TABLE` in `_init_inference.py`):

      - `signup_date`: ISO dates -> iso_date detector -> date_shift
      - `zip_code`: 5-digit US ZIPs -> us_zip detector -> truncate
      - `card_number`: Luhn-valid 16-digit PANs (standard test card
        numbers) -> pan detector -> fpe
      - `account_id`: 6-digit unique integers -> hash (whether STORM
        routes it through a numeric-id detector or the no-detector-match
        likely-unique-integer fallback, both map to `strategy: hash` in
        `_infer_strategy_for_column`)
    """
    csv = tmp_path / "accounts.csv"
    pd.DataFrame(
        {
            "signup_date": [
                "2020-01-15",
                "2020-02-20",
                "2020-03-05",
                "2020-04-30",
            ],
            "zip_code": ["10001", "90210", "60601", "94105"],
            "card_number": [
                "4111111111111111",
                "4012888888881881",
                "5500005555555559",
                "4000000000000002",
            ],
            "account_id": [500001, 500002, 500003, 500004],
        }
    ).to_csv(csv, index=False)
    return csv


def test_init_scaffold_round_trips_date_shift_truncate_fpe(
    csv_with_date_zip_pan_id: Path, tmp_path: Path
):
    """`decoy init <file>` on data with date/zip/PAN/id columns must produce
    a YAML that (a) picks date_shift/truncate/fpe/hash per the inference
    table and (b) validates cleanly through the REAL engine `PipelineConfig`,
    imported independently here (not reusing the CLI's own validator) so
    this test genuinely proves admissibility rather than testing itself.

    Before the fix, `_emit_column_yaml` wrote a `params:` block under all
    three of these strategies (`params: {range_days: 30}` for date_shift,
    `params: {keep: 3}` for truncate, `params: {key_label: default}` for
    fpe). `ColumnConfig` (decoy_engine.config._tables) has no `params`
    field and `extra="forbid"`, so every one of those three columns would
    raise a pydantic ValidationError here -- see
    `test_old_phantom_params_shape_fails_validation` below, which pins
    that failure mode directly against the engine.
    """
    from decoy_engine.config import PipelineConfig

    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", str(csv_with_date_zip_pan_id), "--out", str(out), "--quiet"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr

    body = out.read_text(encoding="utf-8")
    assert "strategy: date_shift" in body
    assert "strategy: truncate" in body
    assert "strategy: fpe" in body
    assert "strategy: hash" in body
    # The phantom container must never appear.
    assert "params:" not in body

    parsed = yaml.safe_load(body)
    # No exception == the scaffold is admissible by the engine's own schema.
    PipelineConfig.model_validate(parsed)


def test_init_scaffold_actually_runs_and_pan_stays_luhn_valid(
    csv_with_date_zip_pan_id: Path, tmp_path: Path
):
    """Two-model-gate HIGH finding: `PipelineConfig.model_validate` passing
    (the assertion above) is a WEAKER property than the scaffold being
    RUNNABLE. hash/fpe/date_shift additionally require `namespace:` at
    RUNTIME -- `ColumnConfig.namespace` defaults to None with no
    compile-time check, so a scaffold missing it passes `decoy validate
    config` and then fails `decoy run` with exit 3
    (`<strategy>_requires_namespace`, execution/_strategies/_hash.py,
    _fpe.py, _date_shift.py).

    This test drives `decoy init` then a REAL `decoy run` on the generated
    config end to end via `CliRunner`, and additionally asserts the masked
    PAN column is Luhn-valid (FPE HIGH finding: an fpe column with no
    `provider_config` defaults `validate_luhn` False, so the checksum is
    never recomputed -- engine `_fpe.py`, `transforms/fpe.py`). It FAILS on
    the pre-namespace / pre-provider_config scaffold and PASSES after the
    fix in `_emit_column_yaml`.
    """
    out = tmp_path / "pipeline.yaml"
    init_result = runner.invoke(
        app, ["init", str(csv_with_date_zip_pan_id), "--out", str(out), "--quiet"]
    )
    assert init_result.exit_code == 0, init_result.stdout + init_result.stderr

    run_result = runner.invoke(app, ["run", str(out)])
    assert run_result.exit_code == 0, (
        f"scaffold failed to run (exit {run_result.exit_code}): {run_result.output}"
    )

    output_path = tmp_path / "accounts.masked.csv"
    assert output_path.exists(), "decoy run did not write the scaffolded output path"

    masked = pd.read_csv(output_path, dtype=str)
    assert "card_number" in masked.columns
    pans = masked["card_number"].tolist()
    assert len(pans) == 4
    for pan in pans:
        assert _luhn_valid(pan), f"masked PAN {pan!r} is not Luhn-valid"


def test_old_phantom_params_shape_fails_validation(tmp_path: Path):
    """Pins the exact failure mode the fix closes: a `params:` block on a
    masking column is rejected by the real engine `ColumnConfig`
    (`extra="forbid"`, no `params` field). This is what
    `decoy init <file>` used to emit for date_shift columns; if this stops
    raising, `ColumnConfig`'s schema changed underneath the CLI and the
    scaffolder's assumptions need re-checking.
    """
    import pydantic
    from decoy_engine.config import PipelineConfig

    input_path = tmp_path / "accounts.csv"
    output_path = tmp_path / "accounts.masked.csv"
    phantom_body = f"""\
version: 1

global_settings:
  seed: 42

sources:
  data:
    type: file
    format: csv
    path: {input_path.as_posix()!r}

tables:
  - name: data
    columns:
      - name: signup_date
        strategy: date_shift
        params:
          range_days: 30

targets:
  data:
    type: file
    format: csv
    path: {output_path.as_posix()!r}
"""
    parsed = yaml.safe_load(phantom_body)
    with pytest.raises(pydantic.ValidationError):
        PipelineConfig.model_validate(parsed)
