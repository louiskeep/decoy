"""`decoy fit --rows`: a row limit with a seeded sample spread across the whole file.

Owner decision 2026-11-10. A file over the limit is fitted on a random sample
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
    from decoy.cli.gen import _fit as fit_module

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


# --- sampling by logical record: blank lines must not shift the chosen rows -------------------

_RECORDS = 5


def _record_lines(
    *, header: str = "idx,name,amount", n: int = _RECORDS, col0_multiline: bool = False
) -> tuple[str, list[str]]:
    if col0_multiline:
        return header, [f'"q{i}\n\nz",{i},{i}.5' for i in range(n)]
    return header, [f"{i},n{i},{i}.5" for i in range(n)]


def _with_blanks(
    header: str,
    records: list[str],
    *,
    before_header: str = "",
    after_header: str | None = None,
    interior: dict[int, str] | None = None,
    trailing: str = "",
    eol: str = "\n",
) -> str:
    """A CSV whose blank lines sit where the arguments say; `interior[i]` follows record i."""
    interior = interior or {}
    lines = [header]
    if after_header is not None:
        lines.append(after_header)
    for i, rec in enumerate(records):
        lines.append(rec)
        if i in interior:
            lines.append(interior[i])
    return before_header + eol.join(lines) + eol + trailing


def _twin_fit_bytes(
    tmp_path: Path, name: str, header: str, records: list[str], kept: list[int]
) -> bytes:
    """The snapshot of a clean file holding exactly the `kept` records (same file name)."""
    twin_dir = tmp_path / "twin"
    twin_dir.mkdir(exist_ok=True)
    twin = twin_dir / name
    twin.write_text("\n".join([header, *(records[i] for i in kept)]) + "\n", encoding="utf-8")
    out = twin_dir / "snap.json"
    assert _fit(twin, out).exit_code == 0
    return out.read_bytes()


_BLANK_CASES = {
    "leading_blank": {"before_header": "\n"},
    "leading_whitespace_line": {"before_header": "   \n"},
    "several_leading_blanks": {"before_header": "\n\n  \n"},
    "blank_after_header": {"after_header": ""},
    "interior_blank": {"interior": {1: ""}},
    "interior_whitespace_only": {"interior": {1: "   "}},
    "interior_tab_only": {"interior": {2: "\t"}},
    "many_interior_blanks": {"interior": {0: "", 1: " ", 3: ""}},
    "trailing_blank": {"trailing": "\n"},
    "trailing_blanks_and_whitespace": {"trailing": "\n  \n\n"},
    "everywhere": {"before_header": "\n", "interior": {0: "", 2: "  "}, "trailing": "\n\n"},
    "crlf_with_blanks": {"before_header": "\r\n", "interior": {1: ""}, "eol": "\r\n"},
}


@pytest.mark.parametrize("keep", [1, 2, 3, 4])
@pytest.mark.parametrize("case", list(_BLANK_CASES))
def test_blank_lines_do_not_shift_the_sampled_records(tmp_path: Path, case: str, keep: int) -> None:
    header, records = _record_lines()
    src = tmp_path / "blanks.csv"
    src.write_bytes(_with_blanks(header, records, **_BLANK_CASES[case]).encode("utf-8"))  # type: ignore[arg-type]
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", str(keep))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"], payload["row_count"]) == (
        keep,
        _RECORDS,
        keep,
    )
    assert list(payload["columns"]) == ["idx", "name", "amount"]
    kept = sample_positions(_RECORDS, keep, 42, keep_order=True).tolist()
    assert out.read_bytes() == _twin_fit_bytes(tmp_path, "blanks.csv", header, records, kept)


def test_a_blank_line_before_the_header_keeps_the_real_header(tmp_path: Path) -> None:
    header, records = _record_lines()
    src = tmp_path / "lead.csv"
    src.write_text(_with_blanks(header, records, before_header="\n"), encoding="utf-8")
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", "2")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["columns"] == {"idx": "numeric", "name": "categorical", "amount": "numeric"}
    assert payload["row_count"] == 2
    kept = sample_positions(_RECORDS, 2, 42, keep_order=True).tolist()
    assert out.read_bytes() == _twin_fit_bytes(tmp_path, "lead.csv", header, records, kept)


@pytest.mark.parametrize("seed_rows", [(_RECORDS, 1), (_RECORDS, 4), (40, 7)])
def test_blank_lines_everywhere_still_pick_the_seeded_records(
    tmp_path: Path, seed_rows: tuple[int, int]
) -> None:
    n, k = seed_rows
    header, records = _record_lines(n=n)
    interior = {i: ("" if i % 3 else "  ") for i in range(0, n, 2)}
    src = tmp_path / "many.csv"
    src.write_text(
        _with_blanks(header, records, before_header="\n\n", interior=interior, trailing="\n"),
        encoding="utf-8",
    )
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", str(k))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["rows_total"] == n
    kept = sample_positions(n, k, 42, keep_order=True).tolist()
    assert out.read_bytes() == _twin_fit_bytes(tmp_path, "many.csv", header, records, kept)


def test_quoted_newlines_in_column_zero_with_blank_lines(tmp_path: Path) -> None:
    header, records = _record_lines(header="note,idx,amount", col0_multiline=True)
    src = tmp_path / "col0.csv"
    src.write_text(
        _with_blanks(header, records, before_header="\n", interior={1: "", 3: " "}, trailing="\n"),
        encoding="utf-8",
    )
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", "3")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (3, _RECORDS)
    assert list(payload["columns"]) == ["note", "idx", "amount"]
    kept = sample_positions(_RECORDS, 3, 42, keep_order=True).tolist()
    assert out.read_bytes() == _twin_fit_bytes(tmp_path, "col0.csv", header, records, kept)


def test_a_bom_with_blank_lines_and_short_rows(tmp_path: Path) -> None:
    header, records = _record_lines()
    records[2] = "2,n2"  # a short row: the missing cell is null
    src = tmp_path / "bom.csv"
    src.write_bytes(
        _with_blanks(header, records, interior={0: "", 3: "  "}, trailing="\n").encode("utf-8-sig")
    )
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", "3")
    assert result.exit_code == 0, result.output
    assert list(json.loads(result.stdout)["columns"]) == ["idx", "name", "amount"]
    kept = sample_positions(_RECORDS, 3, 42, keep_order=True).tolist()
    assert out.read_bytes() == _twin_fit_bytes(tmp_path, "bom.csv", header, records, kept)


def test_a_sampled_cell_is_parsed_as_the_file_spells_it(tmp_path: Path) -> None:
    """Sampling must not change what a cell means: leading zeros, NA words, empty and quoted cells."""
    rows = 40
    lines = ["idx,code,flag,note"]
    for i in range(rows):
        flag = ["NA", "yes", "", "null"][i % 4]
        lines.append(f'{i},{i % 7:03d},{flag},"a, ""b"" {i}"')
    src = tmp_path / "cells.csv"
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sampled = tmp_path / "sampled.json"
    assert _fit(src, sampled, "--rows", "30").exit_code == 0
    kept = sample_positions(rows, 30, 42, keep_order=True).tolist()
    # The same 30 records written out as their own file fit to the same bytes.
    assert sampled.read_bytes() == _twin_fit_bytes(tmp_path, "cells.csv", lines[0], lines[1:], kept)


@pytest.mark.parametrize("extra", [(), ("--rows", "1000")])
def test_a_file_with_blank_lines_under_the_limit_is_unchanged(
    tmp_path: Path, extra: tuple[str, ...]
) -> None:
    from decoy_engine import distribution_snapshot_document

    header, records = _record_lines()
    src = tmp_path / "under.csv"
    src.write_text(
        _with_blanks(header, records, before_header="\n", interior={1: "  "}, trailing="\n"),
        encoding="utf-8",
    )
    expected = json.dumps(
        distribution_snapshot_document(pd.read_csv(src), source_label=src.name), indent=1
    ).encode("utf-8")
    out = tmp_path / "snap.json"
    result = _fit(src, out, *extra)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (payload["rows_used"], payload["rows_total"]) == (_RECORDS, _RECORDS)
    assert out.read_bytes() == expected


def test_a_file_changed_between_the_two_passes_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _small_csv(tmp_path)
    real = pd.read_csv
    calls = {"n": 0}

    def growing(*args: Any, **kwargs: Any) -> Any:
        if "chunksize" in kwargs:
            calls["n"] += 1
            if calls["n"] == 2:  # the select pass: a record arrives after the count
                with src.open("a", encoding="utf-8") as fh:
                    fh.write("99,CA,1.5\n")
        return real(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", growing)
    out = tmp_path / "snap.json"
    result = _fit(src, out, "--rows", "20")
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["code"] == "fit_source_changed"
    assert not out.exists()


@pytest.mark.parametrize(
    "extra",
    [
        (),
        ("--rows", "2"),
        ("--epsilon", "1.0", "--delta", "1e-6", "--dp-text", "state", "--dp-allow-omit"),
    ],
)
def test_an_unreadable_source_error_carries_no_exception_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    import typer

    raised: list[BaseException] = []

    class Recording(typer.Exit):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            raised.append(self)

    monkeypatch.setattr(typer, "Exit", Recording)
    src = tmp_path / "bad.csv"
    src.write_bytes(b"a,b\n\xff\xfe\x00,2\n3,4\n")
    result = _fit(src, tmp_path / "snap.json", *extra)
    assert result.exit_code == EXIT_USAGE, result.output
    assert "could not read" in json.loads(result.stdout)["error"]
    assert raised
    assert all(e.__context__ is None and e.__cause__ is None for e in raised)


def _over_wide_csv(path: Path, wide_line: int, rows: int = 5) -> Path:
    lines = ["a,b,c"] + [f"{i},v{i},w{i}" for i in range(rows)]
    lines[wide_line] += ",EXTRA"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("extra", [(), ("--rows", "1")], ids=["under-limit", "sampled"])
@pytest.mark.parametrize("wide_line", [1, 3], ids=["first-record", "later-record"])
def test_an_over_wide_record_is_refused_not_fitted(
    tmp_path: Path, wide_line: int, extra: tuple[str, ...]
) -> None:
    # With pandas' default index rule an over-wide first record turned column `a` into the index
    # and shifted every value left (`a="v1"`); the file must be refused, never fitted shifted.
    src = _over_wide_csv(tmp_path / "wide.csv", wide_line)
    out = tmp_path / "snap.json"
    result = _fit(src, out, *extra)
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()
    assert "EXTRA" not in result.output


def test_an_excluded_over_wide_first_record_cannot_shift_the_sample(tmp_path: Path) -> None:
    src = tmp_path / "wide.csv"
    src.write_text("a,b,c\n0,x,y,EXTRA\n1,p,q\n2,u,v\n3,m,n\n", encoding="utf-8")
    result = _fit(src, tmp_path / "snap.json", "--rows", "1")
    assert result.exit_code == EXIT_USAGE, result.output
