"""`decoy scan` over positional files (SCAN-MULTI S1c.1): names, header flags, card, `--json`,
and the value-free `--output`.

Every data cell below carries a unique canary. Header cells are column names and are printed
by design, so they never hold one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def _canary(tag: str, n: int) -> str:
    return f"ZQCANARY{tag}{n}"


def _csv(path: Path, tag: str, rows: int = 4) -> Path:
    pd.DataFrame(
        {
            "id": list(range(rows)),
            "label": [_canary(tag, i) for i in range(rows)],
            "mail": [f"{_canary(tag, i).lower()}@example.com" for i in range(rows)],
        }
    ).to_csv(path, index=False)
    return path


def _parquet(path: Path, tag: str) -> Path:
    pd.DataFrame({"pid": [1, 2, 3], "note": [_canary(tag, i) for i in range(3)]}).to_parquet(path)
    return path


@pytest.fixture
def spy_engine(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Records every `scan_sources` call; the usage-error tests assert it stays empty."""
    import decoy_engine

    calls: list[object] = []
    real = decoy_engine.scan_sources

    def spy(*args: object, **kwargs: object):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(decoy_engine, "scan_sources", spy)
    return calls


# -- T2-multi ---------------------------------------------------------------------------


def test_three_files_become_three_tables_in_argument_order(tmp_path: Path) -> None:
    paths = [_csv(tmp_path / n, n[0]) for n in ("b.csv", "a.csv", "c.csv")]
    args = ["scan", *map(str, paths), "--has-header"]
    as_json = json.loads(runner.invoke(app, [*args, "--json"]).stdout)
    assert [t["name"] for t in as_json["tables"]] == ["b", "a", "c"]
    assert as_json["scan_schema"] == "scan-set/v1"
    card = runner.invoke(app, args)
    assert card.exit_code == 0, card.output
    assert card.stdout.index("b <-") < card.stdout.index("a <-") < card.stdout.index("c <-")


def test_table_names_are_normalised(tmp_path: Path) -> None:
    a = _csv(tmp_path / "2024 Sales-Q1.csv", "q")
    doc = json.loads(
        runner.invoke(
            app, ["scan", str(a), str(_csv(tmp_path / "ok.csv", "o")), "--has-header", "--json"]
        ).stdout
    )
    assert [t["name"] for t in doc["tables"]] == ["t_2024_sales_q1", "ok"]


# -- T2-header-required -----------------------------------------------------------------


def test_csv_without_a_header_flag_is_a_usage_error_before_any_read(
    tmp_path: Path, spy_engine: list[object]
) -> None:
    src = _csv(tmp_path / "x.csv", "x")
    result = runner.invoke(app, ["scan", str(src)])
    assert result.exit_code == 1
    assert "x.csv" in result.output
    assert "--has-header" in result.output and "--no-header" in result.output
    assert spy_engine == []


def test_single_parquet_needs_no_header_flag(tmp_path: Path) -> None:
    assert runner.invoke(app, ["scan", str(_parquet(tmp_path / "p.parquet", "p"))]).exit_code == 0


# -- T2-headerless ----------------------------------------------------------------------


def test_headerless_file_profiles_the_first_row_as_data(tmp_path: Path) -> None:
    src = tmp_path / "raw.csv"
    src.write_text("1,alpha\n2,beta\n3,gamma\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["scan", str(src), "--no-header", "--column-names", "id,word", "--show-fields", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 3
    assert [f["name"] for f in payload["fields"]] == ["id", "word"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--no-header"],
        ["--has-header", "--column-names", "a,b"],
        ["--no-header", "--column-names", "a,a"],
    ],
)
def test_header_flag_combinations_that_cannot_work_are_usage_errors(
    tmp_path: Path, spy_engine: list[object], extra: list[str]
) -> None:
    src = tmp_path / "raw.csv"
    src.write_text("1,alpha\n", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(src), *extra])
    assert result.exit_code == 1
    assert spy_engine == []


def test_column_names_need_exactly_one_csv(tmp_path: Path) -> None:
    a, b = _csv(tmp_path / "a.csv", "a"), _csv(tmp_path / "b.csv", "b")
    result = runner.invoke(app, ["scan", str(a), str(b), "--no-header", "--column-names", "x,y,z"])
    assert result.exit_code == 1


# -- T2-tsv -----------------------------------------------------------------------------


def test_tsv_is_read_with_a_tab_delimiter(tmp_path: Path) -> None:
    src = tmp_path / "t.tsv"
    src.write_text("a\tb\tc\n1\tx\ty\n2\tz\tw\n", encoding="utf-8")
    payload = json.loads(runner.invoke(app, ["scan", str(src), "--has-header", "--json"]).stdout)
    assert payload["field_count"] == 3
    out = tmp_path / "scan.json"
    runner.invoke(app, ["scan", str(src), "--has-header", "-o", str(out)])
    descriptor = json.loads(out.read_text())["tables"][0]["descriptor"]
    assert descriptor["format"] == "csv" and descriptor["delimiter"] == "\t"


# -- T2-collision -----------------------------------------------------------------------


def test_two_files_with_one_stem_are_refused_before_any_read(
    tmp_path: Path, spy_engine: list[object]
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    one, two = _csv(tmp_path / "a" / "x.csv", "1"), _csv(tmp_path / "b" / "x.csv", "2")
    result = runner.invoke(app, ["scan", str(one), str(two), "--has-header"])
    assert result.exit_code == 1
    assert "'x'" in result.output
    assert spy_engine == []


# -- T2-atomic --------------------------------------------------------------------------


def test_a_failing_table_exits_3_and_writes_no_output(tmp_path: Path) -> None:
    good = _csv(tmp_path / "good.csv", "g")
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"ZQCANARYBAD this is not parquet")
    out = tmp_path / "scan.json"
    result = runner.invoke(app, ["scan", str(good), str(bad), "--has-header", "-o", str(out)])
    assert result.exit_code == 3
    assert not out.exists()
    assert "'bad'" in result.output
    assert "ZQCANARY" not in result.output


# -- T2-parquet-compat ------------------------------------------------------------------

# The flat keys a single-file `--json` has always carried, and their JSON types.
_FLAT_GOLDEN: dict[str, type | tuple[type, ...]] = {
    "command": str,
    "status": str,
    "source": str,
    "row_count": int,
    "field_count": int,
    "sample_strategy": str,
    "pii_candidate_count": int,
    "pii_note": str,
    "reid_risk_score": (int, float),
    "quasi_identifier_groups": list,
    "saved": type(None),
}


def test_single_parquet_json_keeps_the_flat_keys(tmp_path: Path) -> None:
    src = _parquet(tmp_path / "p.parquet", "p")
    payload = json.loads(runner.invoke(app, ["scan", str(src), "--json"]).stdout)
    assert set(payload) == set(_FLAT_GOLDEN)
    for key, kinds in _FLAT_GOLDEN.items():
        assert isinstance(payload[key], kinds), key


# -- T2-output-core / T2-output-stream-core ---------------------------------------------


def _no_detail(doc: object) -> bool:
    if isinstance(doc, dict):
        return "detail" not in doc and all(_no_detail(v) for v in doc.values())
    if isinstance(doc, list):
        return all(_no_detail(v) for v in doc)
    return True


@pytest.mark.parametrize("count", [1, 3])
def test_output_is_the_value_free_core(tmp_path: Path, count: int) -> None:
    paths = [str(_parquet(tmp_path / "p0.parquet", "p"))]
    paths += [str(_csv(tmp_path / f"c{i}.csv", f"c{i}")) for i in range(count - 1)]
    out = tmp_path / "scan.json"
    args = ["scan", *paths, "--has-header", "-o", str(out)]
    assert runner.invoke(app, args).exit_code == 0
    text = out.read_text()
    doc = json.loads(text)
    assert doc["scan_schema"] == "scan-set/v1" and len(doc["tables"]) == count
    assert _no_detail(doc)
    assert "ZQCANARY" not in text
    assert "top_values" not in text


def test_output_dash_streams_the_core_and_no_canary(tmp_path: Path) -> None:
    src = _csv(tmp_path / "s.csv", "s")
    result = runner.invoke(app, ["scan", str(src), "--has-header", "-o", "-"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["scan_schema"] == "scan-set/v1" and _no_detail(doc)
    assert "ZQCANARY" not in result.stdout


# -- T2-canary --------------------------------------------------------------------------


def test_no_surface_carries_a_cell_value(tmp_path: Path) -> None:
    a, b = _csv(tmp_path / "a.csv", "a"), _csv(tmp_path / "b.csv", "b")
    p = _parquet(tmp_path / "p.parquet", "p")
    base = ["scan", str(a), str(b), str(p), "--has-header", "--show-fields"]
    for extra in ([], ["--json"], ["--verbose"]):
        result = runner.invoke(app, [*base, *extra], env={"COLUMNS": "400"})
        assert result.exit_code == 0, result.output
        assert "ZQCANARY" not in result.output + result.stdout


def test_error_path_carries_no_cell_value(tmp_path: Path) -> None:
    src = tmp_path / "ragged.csv"
    src.write_text("1,ZQCANARYR1,ZQCANARYR2\n2,ZQCANARYR3\n", encoding="utf-8")
    for flags in (["--no-header", "--column-names", "a,b"],):
        result = runner.invoke(app, ["scan", str(src), *flags])
        assert result.exit_code == 3, result.output
        assert "ZQCANARY" not in result.output


# -- header guard -----------------------------------------------------------------------


def test_a_header_row_that_looks_like_data_warns_and_is_not_named_in_the_core(
    tmp_path: Path,
) -> None:
    src = tmp_path / "people.csv"
    src.write_text("123-45-6789,555-12-3456\n234-56-7890,666-23-4567\n", encoding="utf-8")
    out = tmp_path / "scan.json"
    result = runner.invoke(app, ["scan", str(src), "--has-header", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "people" in result.output and "looks like data" in result.output
    text = out.read_text()
    assert "123-45-6789" not in text and "555-12-3456" not in text
    assert [f["name"] for f in json.loads(text)["tables"][0]["fields"]] == ["c0", "c1"]


def test_an_unexpected_engine_error_text_never_reaches_the_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy_engine

    def boom(*args: object, **kwargs: object):
        raise ValueError("ZQCANARY row value")

    monkeypatch.setattr(decoy_engine, "scan_sources", boom)
    src = _csv(tmp_path / "x.csv", "x")
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["scan", str(src), "--has-header", *extra])
        assert result.exit_code == 3
        assert "ZQCANARY" not in result.output + result.stdout
        assert "ValueError" in result.output
