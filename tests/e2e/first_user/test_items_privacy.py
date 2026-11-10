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
    assert payload["value_policy"] == "flagged-redacted/v1"
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

    assert doc["value_policy"] == "flagged-redacted/v1"
    redacted = doc["redacted_columns"]
    assert redacted
    by_name = {f["name"]: f for f in doc["fields"]}
    tops = [t for name in redacted for t in by_name[name].get("top_values") or []]
    assert tops, "no redacted column kept its top-value slots, so the check proves nothing"
    assert {t["value"] for t in tops} == {"[redacted]"}
    for cell in ("alice@example.com", "111-22-3333"):
        assert cell not in text


def test_c1_demo_scan_file_reads_back(demo_dir: Path) -> None:
    doc = json.loads((demo_dir / "scan.json").read_text(encoding="utf-8"))
    column = doc["redacted_columns"][0]
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
