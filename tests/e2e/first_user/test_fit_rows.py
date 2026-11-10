"""`decoy fit --rows`: a row limit with a seeded sample spread across the whole file.

Owner decision 2026-11-10 (roadmap row 24f). A file over the limit is fitted on a random sample
of N rows (fixed seed), never the first N. Sensitivity detection and the snapshot see the same
sampled rows. The limit comes from `--rows`, else `fit.max_rows` in settings.json, else 1,000,000.
A DP fit (`--epsilon`) never samples.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy import _resources
from decoy.__main__ import app
from decoy._row_sample import sample_positions
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_TOTAL = 50_000
_LATE_FROM = 40_000  # the last 20% of the file
_SSNS = [f"{100 + i:03d}-{20 + i:02d}-{1000 + i * 7:04d}" for i in range(8)]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("DECOY_HOME", str(home))
    return home


def _big_csv(tmp_path: Path) -> Path:
    """50k rows. `tax_ref` holds SSNs only in the last 20%; `idx` is the row number."""
    src = tmp_path / "big.csv"
    ssn = [""] * _LATE_FROM + [_SSNS[i % 8] for i in range(_TOTAL - _LATE_FROM)]
    pd.DataFrame(
        {
            "idx": range(_TOTAL),
            "bucket": [i % 13 for i in range(_TOTAL)],
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * (_TOTAL // 8) + ["CA"] * (_TOTAL % 8),
            "tax_ref": ssn,
        }
    ).to_csv(src, index=False)
    return src


def _small_csv(tmp_path: Path, rows: int = 60) -> Path:
    src = tmp_path / "small.csv"
    pd.DataFrame(
        {
            "idx": range(rows),
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * (rows // 8) + ["CA"] * (rows % 8),
            "amount": [10.5 + i for i in range(rows)],
        }
    ).to_csv(src, index=False)
    return src


def _fit(src: Path, out: Path, *extra: str) -> Any:
    return runner.invoke(app, ["fit", str(src), "-o", str(out), "--json", *extra])


def test_sample_is_spread_across_the_file_so_a_late_sensitive_column_is_withheld(
    tmp_path: Path,
) -> None:
    out = tmp_path / "snap.json"
    result = _fit(_big_csv(tmp_path), out, "--rows", "10000")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (10_000, _TOTAL)
    assert payload["row_count"] == 10_000
    text = out.read_text(encoding="utf-8")
    assert "tax_ref" in json.loads(text)["redacted_columns"]
    assert not any(ssn in text for ssn in _SSNS)
    # The row numbers reach past the first 10,000: the sample came from the whole file.
    assert json.loads(text)["columns"]["idx"]["stats"]["max"] > 40_000


def test_same_file_gives_the_same_sample(tmp_path: Path) -> None:
    src = _big_csv(tmp_path)
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    assert _fit(src, one, "--rows", "5000").exit_code == 0
    assert _fit(src, two, "--rows", "5000").exit_code == 0
    assert one.read_bytes() == two.read_bytes()
    other = tmp_path / "other.json"
    assert _fit(src, other, "--rows", "6000").exit_code == 0
    assert other.read_bytes() != one.read_bytes()


def test_a_file_at_or_under_the_limit_is_unchanged(tmp_path: Path) -> None:
    from decoy_engine import distribution_snapshot_document

    src = _small_csv(tmp_path)
    expected = json.dumps(
        distribution_snapshot_document(pd.read_csv(src), source_label=src.name), indent=1
    ).encode("utf-8")
    for extra in ((), ("--rows", "60"), ("--rows", "1000")):
        out = tmp_path / "snap.json"
        result = _fit(src, out, *extra)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert (payload["rows_used"], payload["rows_total"]) == (60, 60)
        assert out.read_bytes() == expected


def test_human_summary_says_rows_used_of_total(tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    result = runner.invoke(app, ["fit", str(_big_csv(tmp_path)), "-o", str(out), "--rows", "7000"])
    assert result.exit_code == 0, result.output
    assert "fitted on 7,000 of 50,000 rows" in " ".join(result.output.split())
    small = runner.invoke(app, ["fit", str(_small_csv(tmp_path)), "-o", str(out)])
    assert "fitted on 60 of 60 rows" in " ".join(small.output.split())


def test_the_setting_changes_the_default_and_the_flag_wins(tmp_path: Path, _home: Path) -> None:
    src = _small_csv(tmp_path)
    _home.mkdir()
    (_home / "settings.json").write_text(
        json.dumps({"schema_version": "1.0", "fit": {"max_rows": 25}})
    )
    out = tmp_path / "snap.json"
    payload = json.loads(_fit(src, out).stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (25, 60)
    payload = json.loads(_fit(src, out, "--rows", "40").stdout)
    assert payload["rows_used"] == 40


def test_default_limit_is_one_million_with_no_setting() -> None:
    assert _resources.read_fit_max_rows() == 1_000_000


def test_setting_survives_decoy_setup(tmp_path: Path, _home: Path, monkeypatch) -> None:
    monkeypatch.setattr(_resources, "_auto_memory", lambda: 2**33)
    monkeypatch.setattr(_resources, "_auto_threads", lambda: 4)
    _home.mkdir()
    (_home / "settings.json").write_text(
        json.dumps({"schema_version": "1.0", "fit": {"max_rows": 25}})
    )
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    assert _resources.read_fit_max_rows() == 25


@pytest.mark.parametrize("stored", [0, -5, "100", True, 1.5, None])
def test_a_bad_stored_setting_is_a_usage_error(tmp_path: Path, _home: Path, stored: Any) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text(
        json.dumps({"schema_version": "1.0", "fit": {"max_rows": stored}})
    )
    result = _fit(_small_csv(tmp_path), tmp_path / "snap.json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["code"] == "fit_rows_setting_invalid"
    assert not (tmp_path / "snap.json").exists()


@pytest.mark.parametrize("bad", ["0", "-3", "abc", "1.5", "", "1e3"])
def test_bad_rows_value_is_a_usage_error(tmp_path: Path, bad: str) -> None:
    out = tmp_path / "snap.json"
    result = _fit(_small_csv(tmp_path), out, "--rows", bad)
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["code"] == "fit_rows_invalid"
    assert not out.exists()


def test_rows_with_epsilon_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    result = _fit(
        _small_csv(tmp_path),
        out,
        "--rows",
        "10",
        "--epsilon",
        "1.0",
        "--delta",
        "1e-6",
        "--dp-number",
        "amount:0:200",
        "--dp-text",
        "state",
        "--dp-allow-omit",
    )
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["code"] == "dp_mode_rows_unsupported"
    assert not out.exists()


def test_dp_fit_ignores_the_setting_and_uses_every_row(
    tmp_path: Path, _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text(
        json.dumps({"schema_version": "1.0", "fit": {"max_rows": 5}})
    )
    seen: dict[str, int] = {}

    def _fake(df: Any, schema: Any, **kw: Any) -> dict[str, Any]:
        seen["rows"] = len(df)
        return {
            "row_count": len(df),
            "columns": {"state": {"kind": "categorical"}},
            "joints": [],
            "dp": {"schema": "dps-marginal/v3"},
        }

    monkeypatch.setattr("decoy_engine.quality.check_dp_fit_request", lambda *a, **k: None)
    monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _fake)
    result = _fit(
        _small_csv(tmp_path),
        tmp_path / "snap.json",
        "--epsilon",
        "1.0",
        "--delta",
        "1e-6",
        "--dp-text",
        "state",
        "--dp-allow-omit",
    )
    assert result.exit_code == 0, result.output
    assert seen["rows"] == 60
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (60, 60)


def _bucket_counts(snapshot: Path, buckets: int) -> list[int]:
    """Rows per `bucket` value in the snapshot (values 0..buckets-1, so sorted order is by value)."""
    exact = json.loads(snapshot.read_text(encoding="utf-8"))["columns"]["bucket"]["stats"][
        "exact_values"
    ]
    assert exact["values"] == list(range(buckets))
    return exact["counts"]


def _expected_bucket_counts(total: int, limit: int, buckets: int) -> list[int]:
    kept = sample_positions(total, limit, 42, keep_order=True)
    return np.bincount(kept % buckets, minlength=buckets).tolist()


def test_sample_membership_is_pinned(tmp_path: Path) -> None:
    """The fitted rows are exactly the seeded positions, in file order (idx is the row number)."""
    out = tmp_path / "snap.json"
    assert _fit(_big_csv(tmp_path), out, "--rows", "10000").exit_code == 0
    assert _bucket_counts(out, 13) == _expected_bucket_counts(_TOTAL, 10_000, 13)


def _mixed_csv(path: Path, *, v_bad: int | None = None, d_bad: int | None = None) -> Path:
    rows = 2_000
    v = [str(i) for i in range(rows)]
    d = [f"2024-01-{(i % 28) + 1:02d}" for i in range(rows)]
    if v_bad is not None:
        v[v_bad] = "abc"
    if d_bad is not None:
        d[d_bad] = "not-a-date"
    pd.DataFrame({"v": v, "d": d, "state": ["CA", "NY"] * (rows // 2)}).to_csv(path, index=False)
    return path


def test_an_excluded_row_cannot_change_the_result(tmp_path: Path) -> None:
    limit = 500
    kept = set(sample_positions(2_000, limit, 42, keep_order=True).tolist())
    excluded = next(i for i in range(2_000) if i not in kept)
    src = tmp_path / "data.csv"
    runs: list[tuple[bytes, dict[str, str]]] = []
    for bad in (
        {},
        {"v_bad": excluded},
        {"d_bad": excluded},
        {"v_bad": excluded, "d_bad": excluded},
    ):
        _mixed_csv(src, **bad)
        out = tmp_path / "snap.json"
        result = _fit(src, out, "--rows", str(limit), "--parse-dates", "d")
        assert result.exit_code == 0, result.output
        runs.append((out.read_bytes(), json.loads(result.stdout)["columns"]))
    assert runs[0][1]["v"] == "numeric"
    assert all(run == runs[0] for run in runs)
    # Control: the same damage inside the sample does change the column kind.
    inside = min(kept)
    _mixed_csv(src, v_bad=inside)
    result = _fit(src, tmp_path / "snap.json", "--rows", str(limit), "--parse-dates", "d")
    assert json.loads(result.stdout)["columns"]["v"] != "numeric"


def test_an_oversized_file_is_never_fully_materialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import fit as fit_module

    monkeypatch.setattr(fit_module, "_COUNT_CHUNK", 400)
    seen: list[int] = []
    real = pd.read_csv

    def spy(*args: Any, **kwargs: Any) -> Any:
        out = real(*args, **kwargs)
        if isinstance(out, pd.DataFrame):
            seen.append(len(out))
            return out

        def chunks() -> Any:
            for chunk in out:
                seen.append(len(chunk))
                yield chunk

        return chunks()

    monkeypatch.setattr(pd, "read_csv", spy)
    result = _fit(_mixed_csv(tmp_path / "data.csv"), tmp_path / "snap.json", "--rows", "300")
    assert result.exit_code == 0, result.output
    assert max(seen) <= 400  # the sample (300) or one counting chunk, never the 2,000-row file
    assert json.loads(result.stdout)["rows_total"] == 2_000


def test_quoted_multiline_cells_count_as_one_record(tmp_path: Path) -> None:
    rows = 3_000
    src = tmp_path / "notes.csv"
    pd.DataFrame(
        {
            "idx": range(rows),
            "bucket": [i % 11 for i in range(rows)],
            "note": [f"line one {i}\nline two\n\nline four" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", "1000")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (1_000, rows)
    assert _bucket_counts(out, 11) == _expected_bucket_counts(rows, 1_000, 11)


def test_a_bad_setting_error_carries_no_exception_context(
    tmp_path: Path, _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import fit as fit_module

    raised: list[BaseException] = []

    class Recording(fit_module._FitUsageError):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            raised.append(self)

    monkeypatch.setattr(fit_module, "_FitUsageError", Recording)
    _home.mkdir()
    (_home / "settings.json").write_text(
        json.dumps({"schema_version": "1.0", "fit": {"max_rows": 0}})
    )
    result = _fit(_small_csv(tmp_path), tmp_path / "snap.json")
    assert json.loads(result.stdout)["code"] == "fit_rows_setting_invalid"
    assert raised
    assert all(e.__context__ is None and e.__cause__ is None for e in raised)
