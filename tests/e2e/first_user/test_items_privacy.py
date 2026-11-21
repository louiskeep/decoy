"""Cell values a first-time user could leak through `decoy fit` and scan files.

QA item High 5 (docs/records/2026-11-08-cli-qa-first-user.md): a plain
`decoy fit` copied raw SSNs and names into the snapshot's `top_values`. The
`test_f*` cells reproduce that run against a small patients fixture and check the
file, stdout and stderr for the fixture's values.

The `test_c*` cells cover the scan side: `decoy demo` wrote the raw profile
(`to_dict()`) as its scan file, `decoy explain security` said a saved scan can
hold top values, and `scan show` and `scan fields` must print nothing from a raw
`detail` member, the shape the engine writes for `scan_set_to_dict(detail=True)`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml
from decoy_engine import profile_columns
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()
SENTINEL = "ZQDETAILSENTINEL"
_WIDE = {"COLUMNS": "10000"}

_ROWS = 60
# Eight repeating SSNs: a unique-per-row column is not sampled into top_values.
_SSNS = [f"{100 + i % 8:03d}-{20 + i % 8:02d}-{1000 + (i % 8) * 7:04d}" for i in range(_ROWS)]
_NAMES = [f"Zelda Quillfeather{i:02d}" for i in range(_ROWS)]
_IDS = [f"PT-{7000 + i}" for i in range(_ROWS)]
_FIXTURE_VALUES = [*_SSNS, *_NAMES, *_IDS]


def _patients(tmp_path: Path) -> Path:
    src = tmp_path / "patients.csv"
    pd.DataFrame(
        {
            "patient_id": _IDS,
            "name": _NAMES,
            "ssn": _SSNS,
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * (_ROWS // 8) + ["CA"] * (_ROWS % 8),
            "amount": [10.5 + i for i in range(_ROWS)],
        }
    ).to_csv(src, index=False)
    return src


def _fit(tmp_path: Path, *extra: str) -> tuple[Any, Path]:
    out = tmp_path / "snap.json"
    result = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out), *extra])
    return result, out


def _leaks(text: str) -> list[str]:
    return [v for v in _FIXTURE_VALUES if v in text]


def _stderr(result: Any) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


def test_f1_default_fit_withholds_sensitive_values(tmp_path: Path) -> None:
    result, out = _fit(tmp_path)
    assert result.exit_code == 0, result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert "ssn" in doc["redacted_columns"]
    assert _leaks(out.read_text(encoding="utf-8")) == []
    assert _leaks(result.output) == []
    assert _leaks(_stderr(result)) == []
    assert "ssn" in result.output
    assert "withheld" in result.output


def test_f2_include_values_keeps_values_and_warns(tmp_path: Path) -> None:
    result, out = _fit(tmp_path, "--include-values")
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["value_policy"] == "raw"
    assert any(ssn in text for ssn in _SSNS)
    warning = " ".join((result.output + _stderr(result)).split())
    assert "holds real values" in warning
    assert "ssn" in warning
    assert str(out) in warning.replace("\n", "")


def test_f3_json_payload_names_policy_and_columns(tmp_path: Path) -> None:
    result, _ = _fit(tmp_path, "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["value_policy"] == "flagged-redacted/v2"
    assert "ssn" in payload["redacted_columns"]
    assert _leaks(result.stdout) == []


def test_f4_listed_columns_come_from_the_document_not_the_output_path(tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    out.write_text(
        json.dumps({"value_policy": "flagged-redacted/v1", "redacted_columns": ["forged_col"]}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out), "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    payload = json.loads(result.stdout)
    assert payload["redacted_columns"] == doc["redacted_columns"]
    assert "forged_col" not in payload["redacted_columns"]
    human = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out)])
    assert "forged_col" not in human.output
    for name in doc["redacted_columns"]:
        assert name in human.output


def _gen_config(tmp_path: Path, snap: Path, *, real: bool) -> Path:
    col: dict[str, Any] = {"name": "ssn", "type": "statistical", "snapshot_file": str(snap)}
    if real:
        col["allow_real_categories"] = True
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "tables": [{"name": "synthetic", "row_count": 10, "generate_columns": [col]}],
        "targets": {
            "synthetic": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}
        },
    }
    path = tmp_path / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_f5_validate_rejects_withheld_column_until_refit_with_values(tmp_path: Path) -> None:
    _, snap = _fit(tmp_path)
    cfg = _gen_config(tmp_path, snap, real=True)
    redacted = runner.invoke(app, ["validate", "config", str(cfg)])
    assert redacted.exit_code == 1, redacted.output
    assert "statistical_snapshot_values_redacted" in redacted.output
    assert "--include-values" in redacted.output

    refit, snap = _fit(tmp_path, "--include-values")
    assert refit.exit_code == 0, refit.output
    ok = runner.invoke(app, ["validate", "config", str(_gen_config(tmp_path, snap, real=True))])
    assert ok.exit_code == 0, ok.output


_QA_DIAGNOSES = ["Hypertension", "Asthma", "Diabetes", "Migraine", "Arthritis", "Anemia"]
_QA_NOTES = [f"patient Surname{i} called" for i in range(30)]
_QA_CANARIES = ["RARE-HIV-B20", "987654", "1921", *_QA_NOTES]


def _qa_csv(tmp_path: Path) -> Path:
    """The DI models QA frame: 1,000 rows, seed 31, one rare cell in each of four columns.

    The profiler flags every date column, so `visit_date` is withheld on its own and the other
    three columns reach the unflagged floor."""
    rng = np.random.default_rng(31)
    n = 1000
    salary = rng.integers(40, 150, n) * 1000.0
    salary[0] = 987654.0
    diagnosis = rng.choice(_QA_DIAGNOSES, n).astype(object)
    diagnosis[1] = "RARE-HIV-B20"
    days = rng.integers(0, 3650, n)
    visit = pd.Series(pd.Timestamp("2015-01-01") + pd.to_timedelta(days, unit="D"))
    visit[3] = pd.Timestamp("1921-06-15")
    src = tmp_path / "qa.csv"
    pd.DataFrame(
        {
            "salary": salary,
            "diagnosis": diagnosis,
            "note": [_QA_NOTES[i % 30] for i in range(n)],
            "visit_date": visit.dt.strftime("%Y-%m-%d"),
        }
    ).to_csv(src, index=False)
    return src


def test_at_c1_plain_fit_floors_unflagged_columns_and_takes_numeric_bins(tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        [
            "fit",
            str(_qa_csv(tmp_path)),
            "--numeric-bins",
            "17",
            "--parse-dates",
            "visit_date",
            "--json",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert [c for c in _QA_CANARIES if c in text] == []
    assert [c for c in _QA_CANARIES if c in result.stdout] == []
    ranges = doc["columns"]["visit_date"]["stats"]["year_bins"]
    assert ranges
    assert all(set(r) == {"start_year", "end_year", "count"} for r in ranges)
    # Engine contract (engine plan docs/plans/2026-11-20-24f-interior-bin-floor.md, G9): "If
    # `add_numeric_shape` attached an `exact_values` or `quantile_grid` block and that block can be
    # released, the accompanying histogram is one bin `[lo, hi]` holding the finite count." The
    # same plan withdraws the old promise: "The parent plan's promise 'at least `numeric_bins`
    # bins' (parent 4.2, AT-1, AT-C1) is withdrawn." So `--numeric-bins 17` here gives one bin.
    salary = doc["columns"]["salary"]["stats"]
    assert "quantile_grid" in salary or "exact_values" in salary
    assert salary["bin_counts"] == [1000]
    assert len(salary["bin_edges"]) == 2
    assert doc["columns"]["note"]["kind"] == "freetext"
    assert json.loads(result.stdout)["value_policy"] == "flagged-redacted/v2"


def test_at_c1b_numeric_bins_without_a_shape_block_follows_the_finest_step_rule(
    tmp_path: Path,
) -> None:
    """Engine plan G9 and its withdrawal line: with no shape block (under 100 rows, no value held
    by 10 rows) the plain fit uses the finest 1, 2, 5 step, from the requested width up, at which
    every bin holds 0 or at least 10 rows. Ninety rows, 18 per decade, each value twice, 17 bins
    asked: steps 2 and 5 leave bins under 10 rows, so the step is 10 and the result is five bins
    of 18."""
    values = [d * 10 + 0.5 + i % 9 for d in range(5) for i in range(18)]
    src = tmp_path / "decades.csv"
    pd.DataFrame({"x": values}).to_csv(src, index=False)
    out = tmp_path / "snap.json"
    result = runner.invoke(app, ["fit", str(src), "--numeric-bins", "17", "-o", str(out)])
    assert result.exit_code == 0, result.output
    stats = json.loads(out.read_text(encoding="utf-8"))["columns"]["x"]["stats"]
    assert "quantile_grid" not in stats and "exact_values" not in stats
    assert stats["bin_edges"] == [0, 10, 20, 30, 40, 50]
    assert stats["bin_counts"] == [18, 18, 18, 18, 18]
    assert 1 < len(stats["bin_counts"]) <= 17
    assert [c for c in stats["bin_counts"] if 0 < c < 10] == []


def test_at_c2_validate_refuses_a_column_too_small_to_floor(tmp_path: Path) -> None:
    src = tmp_path / "small.csv"
    states = ["CA"] * 6 + ["NY"] * 5 + ["TX"] * 4
    pd.DataFrame({"state": states, "amount": [float(i) for i in range(15)]}).to_csv(
        src, index=False
    )
    snap = tmp_path / "small.snapshot.json"
    fit = runner.invoke(app, ["fit", str(src), "-o", str(snap)])
    assert fit.exit_code == 0, fit.output
    assert "state" in json.loads(snap.read_text(encoding="utf-8"))["redacted_columns"]

    col: dict[str, Any] = {
        "name": "state",
        "type": "statistical",
        "snapshot_file": str(snap),
        "allow_real_categories": True,
    }
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "tables": [{"name": "synthetic", "row_count": 10, "generate_columns": [col]}],
        "targets": {
            "synthetic": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}
        },
    }
    path = tmp_path / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["validate", "config", str(path)])
    assert result.exit_code == 1, result.output
    assert "statistical_snapshot_values_redacted" in result.output
    assert "--include-values" in result.output


def test_f6_include_values_with_epsilon_is_a_usage_error_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("pd.read_csv must not run")

    monkeypatch.setattr(pd, "read_csv", _no_read)
    src = tmp_path / "s.csv"
    src.write_text("state\nCA\nNY\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["fit", str(src), "--include-values", "--epsilon", "1", "--delta", "1e-6",
         "--dp-text", "state", "--json"],
    )  # fmt: skip
    assert result.exit_code == EXIT_USAGE
    assert json.loads(result.stdout)["code"] == "dp_usage_include_values"


def test_f7_snapshot_carries_cell_format_per_column(tmp_path: Path) -> None:
    _, out = _fit(tmp_path)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert all("cell_format" in col for col in doc["columns"].values())


def test_f9_sensitive_column_empty_in_the_head_rows_is_still_withheld(tmp_path: Path) -> None:
    """A row cap on the sensitivity profile would see only blanks here and keep the values."""
    rows, blank = 10_050, 10_010
    late = _SSNS[:8]
    src = tmp_path / "late.csv"
    pd.DataFrame(
        {
            "ssn": [""] * blank + [late[i % 8] for i in range(rows - blank)],
            "amount": [float(i % 97) for i in range(rows)],
        }
    ).to_csv(src, index=False)
    out = tmp_path / "late.json"
    result = runner.invoke(app, ["fit", str(src), "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "ssn" in json.loads(text)["redacted_columns"]
    assert not any(v in text for v in late)


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo") / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out)])
    assert result.exit_code == 0, result.output
    return out


def test_c1_demo_scan_file_redacts_sensitive_values(demo_dir: Path) -> None:
    text = (demo_dir / "scan.json").read_text(encoding="utf-8")
    doc = json.loads(text)

    # The saved scan is the value-free `scan-set/v1` core: no top values, so no cell to redact.
    assert doc["scan_schema"].startswith("scan-set/v1")
    assert "top_values" not in text and "value_policy" not in doc
    assert doc["tables"][0]["fields"], "an empty scan proves nothing"
    for cell in ("alice@example.com", "111-22-3333", "Alice", "Anderson", "1990-01-15"):
        assert cell not in text


def test_c1_demo_scan_file_reads_back(demo_dir: Path) -> None:
    doc = json.loads((demo_dir / "scan.json").read_text(encoding="utf-8"))
    column = next(f["name"] for f in doc["tables"][0]["fields"] if f["pii_candidate"])
    result = runner.invoke(app, ["scan", "show", str(demo_dir / "scan.json"), column])
    assert result.exit_code == 0, result.output


@pytest.fixture
def detail_scan(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4"],
            "first_name": ["Ana", "Ben", "Cy", "Di"],
            "ssn": ["111-22-3333", "222-33-4444", "333-44-5555", "444-55-6666"],
        }
    )
    src = tmp_path / "people.csv"
    df.to_csv(src, index=False)
    core = tmp_path / "core.json"
    assert runner.invoke(app, ["scan", str(src), "--has-header", "-o", str(core)]).exit_code == 0
    doc = json.loads(core.read_text(encoding="utf-8"))
    assert doc["scan_schema"].startswith("scan-set/v1")

    seeded = df.assign(first_name=[f"{SENTINEL}{n}" for n in range(4)])
    detail = profile_columns(seeded, source_label="people.csv", sample_strategy="full").to_dict()
    assert SENTINEL in json.dumps(detail)
    doc["tables"][0]["detail"] = detail
    path = tmp_path / "detail.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "argv",
    [
        ["scan", "show", "{p}", "first_name"],
        ["scan", "show", "{p}", "first_name", "--json"],
        ["scan", "fields", "{p}"],
        ["scan", "fields", "{p}", "--json"],
    ],
)
def test_c3_scan_reads_print_nothing_from_a_raw_detail(detail_scan: Path, argv: list[str]) -> None:
    args = [str(detail_scan) if a == "{p}" else a for a in argv]
    result = runner.invoke(app, args, env=_WIDE)
    assert result.exit_code == 0, result.output
    assert SENTINEL not in result.output
    assert "first_name" in result.output


def test_c4_explain_security_says_saved_scans_hold_no_values() -> None:
    result = runner.invoke(app, ["explain", "security", "--json"])
    assert result.exit_code == 0, result.output
    body = " ".join(json.loads(result.stdout)["body"].split())
    assert "top values" not in body
    assert "never cell values" in body
    assert "A plain run withholds the values of sensitive columns" in body
    assert "--include-values" in body
