"""SP-16: storm analyze parquet + fixed-width format dispatch.

Tests run BEFORE the implementation so they fail first (TDD requirement).

Assertions:
B1. storm analyze reads a parquet fixture and produces a valid STORM profile.
B2. storm analyze reads a fixed-width fixture WITH a layout spec.
B3. storm analyze fixed-width WITHOUT a layout fails closed with a clear error.
B4. --format parquet flag dispatches to the parquet loader.
B5. --format delimited (explicit) still works (delimited is the zero-config default).
B6. Extension-based detection: .parquet extension uses parquet loader without --format.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parquet_fixture(tmp_path: Path) -> Path:
    """A small parquet file with PII-ish columns for STORM analysis."""
    path = tmp_path / "members.parquet"
    pd.DataFrame(
        {
            "member_id": ["M1", "M2", "M3"],
            "first_name": ["Alice", "Bob", "Carol"],
            "email": ["alice@example.com", "bob@example.com", "carol@example.com"],
            "dob": ["1980-01-01", "1990-06-15", "1975-03-22"],
        }
    ).to_parquet(path, index=False)
    return path


@pytest.fixture
def fwf_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A fixed-width file and its layout YAML.

    Layout:
      member_id : cols 0-4   (width 4, 0-indexed start, exclusive end = 4)
      first_name: cols 4-14  (width 10)
      email     : cols 14-34 (width 20)
    """
    fwf_path = tmp_path / "members.fwf"
    # Write fixed-width lines (right-padded with spaces)
    lines = [
        "M001Alice     alice@example.com   ",
        "M002Bob       bob@example.com     ",
        "M003Carol     carol@example.com   ",
    ]
    fwf_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    layout_path = tmp_path / "layout.yaml"
    layout = {
        "columns": [
            {"name": "member_id", "start": 0, "width": 4},
            {"name": "first_name", "start": 4, "width": 10},
            {"name": "email", "start": 14, "width": 20},
        ]
    }
    layout_path.write_text(yaml.dump(layout), encoding="utf-8")
    return fwf_path, layout_path


# ---------------------------------------------------------------------------
# B1. Parquet fixture -> valid STORM profile
# ---------------------------------------------------------------------------


def test_storm_analyze_reads_parquet_fixture(parquet_fixture: Path, tmp_path: Path):
    """B1: storm analyze on a .parquet file produces a valid STORM profile JSON."""
    out = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        ["storm", "analyze", str(parquet_fixture), "--out", str(out)],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    assert out.exists(), "Expected scan output file to be written"
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 3
    field_names = [f["name"] for f in payload["fields"]]
    assert "email" in field_names, f"Expected 'email' in fields. Got: {field_names}"
    assert payload["source_label"] == "members.parquet"


def test_storm_analyze_parquet_json_output(parquet_fixture: Path):
    """B1 extension: parquet with --json emits a structured envelope."""
    result = runner.invoke(
        app,
        ["storm", "analyze", str(parquet_fixture), "--json"],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm analyze"
    assert payload["status"] == "ok"
    assert payload["profile"]["row_count"] == 3


# ---------------------------------------------------------------------------
# B2. Fixed-width WITH layout -> valid STORM profile
# ---------------------------------------------------------------------------


def test_storm_analyze_reads_fixed_width_with_layout(fwf_fixture: tuple[Path, Path], tmp_path: Path):
    """B2: storm analyze on a fixed-width file with --layout produces a valid STORM profile."""
    fwf_path, layout_path = fwf_fixture
    out = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        [
            "storm", "analyze",
            str(fwf_path),
            "--layout", str(layout_path),
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    assert out.exists()
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 3
    field_names = [f["name"] for f in payload["fields"]]
    assert "member_id" in field_names, f"Got field names: {field_names}"
    assert "first_name" in field_names
    assert "email" in field_names


def test_storm_analyze_fixed_width_json_output(fwf_fixture: tuple[Path, Path]):
    """B2 extension: fixed-width + layout with --json emits a valid envelope."""
    fwf_path, layout_path = fwf_fixture
    result = runner.invoke(
        app,
        [
            "storm", "analyze",
            str(fwf_path),
            "--layout", str(layout_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["profile"]["row_count"] == 3


# ---------------------------------------------------------------------------
# B3. Fixed-width WITHOUT layout -> fail closed with clear error
# ---------------------------------------------------------------------------


def test_storm_analyze_fixed_width_without_layout_fails_closed(fwf_fixture: tuple[Path, Path]):
    """B3: a fixed-width file WITHOUT --layout must fail closed with a clear error.

    Column boundaries are ambiguous without a layout spec; guessing would produce
    silently wrong profiles. The CLI must reject this with a typed, actionable error.
    """
    fwf_path, _layout_path = fwf_fixture
    # Pass --format fixed-width but NO --layout
    result = runner.invoke(
        app,
        ["storm", "analyze", str(fwf_path), "--format", "fixed-width"],
    )
    assert result.exit_code != 0, (
        "Expected non-zero exit when --format fixed-width is used without --layout. "
        f"Got exit {result.exit_code}. output: {result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "layout" in combined.lower(), (
        f"Expected 'layout' in error message. Got: {combined}"
    )


def test_storm_analyze_fwf_extension_without_layout_fails_closed(tmp_path: Path):
    """B3 extension: a .fwf extension file without --layout also fails closed.

    Extension-based detection must not silently fall back to CSV guessing.
    """
    fwf_path = tmp_path / "data.fwf"
    fwf_path.write_text("M001Alice     \nM002Bob       \n", encoding="utf-8")

    result = runner.invoke(app, ["storm", "analyze", str(fwf_path)])
    assert result.exit_code != 0, (
        "Expected non-zero exit when .fwf file has no --layout. "
        f"Got exit {result.exit_code}. output: {result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "layout" in combined.lower(), (
        f"Expected 'layout' mention in error. Got: {combined}"
    )


# ---------------------------------------------------------------------------
# B4. --format parquet flag dispatches to parquet loader
# ---------------------------------------------------------------------------


def test_storm_analyze_explicit_format_parquet(parquet_fixture: Path, tmp_path: Path):
    """B4: --format parquet explicitly selects the parquet loader (overrides extension)."""
    out = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        [
            "storm", "analyze",
            str(parquet_fixture),
            "--format", "parquet",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 3


# ---------------------------------------------------------------------------
# B5. --format delimited (explicit) still works
# ---------------------------------------------------------------------------


def test_storm_analyze_explicit_format_delimited(tmp_path: Path):
    """B5: --format delimited explicitly selects CSV loader (default stays working)."""
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(csv_path, index=False)
    out = tmp_path / "scan.json"

    result = runner.invoke(
        app,
        [
            "storm", "analyze",
            str(csv_path),
            "--format", "delimited",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 3


# ---------------------------------------------------------------------------
# B6. Extension-based detection for parquet
# ---------------------------------------------------------------------------


def test_storm_analyze_parquet_extension_auto_detects(parquet_fixture: Path, tmp_path: Path):
    """B6: .parquet extension triggers parquet loader without needing --format parquet."""
    out = tmp_path / "scan.json"
    # No --format flag -- extension should be enough
    result = runner.invoke(
        app,
        ["storm", "analyze", str(parquet_fixture), "--out", str(out)],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 3


# ---------------------------------------------------------------------------
# C-series: malformed layout -> EXIT 1 (usage) with actionable message
# ---------------------------------------------------------------------------


@pytest.fixture
def fwf_data(tmp_path: Path) -> Path:
    """A minimal fixed-width data file for malformed-layout tests."""
    path = tmp_path / "data.fwf"
    path.write_text("M001Alice     alice@example.com   \n", encoding="utf-8")
    return path


def test_malformed_layout_missing_width_exits_usage(fwf_data: Path, tmp_path: Path):
    """C1: A layout column missing 'width' must exit 1 (usage) with an actionable message.

    'width' is required for fixed-width parsing; a missing key must name the
    offending column and key, not bubble up a raw KeyError.
    """
    layout_path = tmp_path / "layout_no_width.yaml"
    layout_path.write_text(
        yaml.dump({"columns": [{"name": "member_id", "start": 0}]}),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["storm", "analyze", str(fwf_data), "--layout", str(layout_path)],
    )
    assert result.exit_code == 1, (
        f"Expected exit 1 (usage) for missing 'width', got {result.exit_code}.\n{result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "width" in combined.lower(), (
        f"Expected 'width' named in error. Got: {combined}"
    )
    assert "column" in combined.lower(), (
        f"Expected 'column' referenced in error. Got: {combined}"
    )


def test_malformed_layout_non_int_width_exits_usage(fwf_data: Path, tmp_path: Path):
    """C2: A layout column with width: 'abc' must exit 1 (usage) with an actionable message.

    Non-integer 'width' must produce a clean error, not a raw ValueError from int().
    """
    layout_path = tmp_path / "layout_bad_width.yaml"
    layout_path.write_text(
        yaml.dump({"columns": [{"name": "member_id", "start": 0, "width": "abc"}]}),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["storm", "analyze", str(fwf_data), "--layout", str(layout_path)],
    )
    assert result.exit_code == 1, (
        f"Expected exit 1 (usage) for non-integer 'width', got {result.exit_code}.\n{result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "width" in combined.lower(), (
        f"Expected 'width' named in error. Got: {combined}"
    )
    assert "integer" in combined.lower() or "int" in combined.lower(), (
        f"Expected 'integer'/'int' hint in error. Got: {combined}"
    )


def test_malformed_layout_columns_is_string_exits_usage(fwf_data: Path, tmp_path: Path):
    """C3: columns: 'id,name' (a string) must exit 1 (usage) with an actionable message.

    Passing a scalar instead of a list for 'columns' must name the problem and
    expected type, not surface a raw 'string indices must be integers' traceback.
    """
    layout_path = tmp_path / "layout_columns_str.yaml"
    layout_path.write_text(
        yaml.dump({"columns": "id,name"}),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["storm", "analyze", str(fwf_data), "--layout", str(layout_path)],
    )
    assert result.exit_code == 1, (
        f"Expected exit 1 (usage) for columns as string, got {result.exit_code}.\n{result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "columns" in combined.lower() or "list" in combined.lower(), (
        f"Expected 'columns' or 'list' in error. Got: {combined}"
    )


def test_malformed_layout_empty_file_exits_usage(fwf_data: Path, tmp_path: Path):
    """C4: An empty/garbage layout file must exit 1 (usage) with an actionable message.

    An empty YAML file parses as None; the validator must catch this and give a
    clear directive rather than surfacing an AttributeError.
    """
    layout_path = tmp_path / "layout_empty.yaml"
    layout_path.write_text("", encoding="utf-8")
    result = runner.invoke(
        app,
        ["storm", "analyze", str(fwf_data), "--layout", str(layout_path)],
    )
    assert result.exit_code == 1, (
        f"Expected exit 1 (usage) for empty layout, got {result.exit_code}.\n{result.output}"
    )
    combined = result.output + (str(result.exception) if result.exception else "")
    assert any(
        kw in combined.lower() for kw in ("columns", "mapping", "layout")
    ), f"Expected actionable keyword in error. Got: {combined}"
