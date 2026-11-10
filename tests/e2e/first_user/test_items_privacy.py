"""Cell values a first-time user could leak through a scan file.

`decoy demo` wrote the raw profile (`to_dict()`), top values and all, as its scan file, and
`decoy explain security` still told users a saved scan can hold top values. A saved scan read
back by `scan show` and `scan fields` must also print nothing from a raw `detail` member, the
shape the engine writes for `scan_set_to_dict(detail=True)`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from decoy_engine import profile_columns
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()
SENTINEL = "ZQDETAILSENTINEL"
_WIDE = {"COLUMNS": "10000"}


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo") / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out)])
    assert result.exit_code == 0, result.output
    return out


def test_demo_scan_file_redacts_sensitive_values(demo_dir: Path) -> None:
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


def test_demo_scan_file_reads_back(demo_dir: Path) -> None:
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
def test_scan_reads_print_nothing_from_a_raw_detail(detail_scan: Path, argv: list[str]) -> None:
    args = [str(detail_scan) if a == "{p}" else a for a in argv]
    result = runner.invoke(app, args, env=_WIDE)
    assert result.exit_code == 0, result.output
    assert SENTINEL not in result.output
    assert "first_name" in result.output


def test_explain_security_says_saved_scans_hold_no_values() -> None:
    result = runner.invoke(app, ["explain", "security", "--json"])
    assert result.exit_code == 0, result.output
    body = " ".join(json.loads(result.stdout)["body"].split())
    assert "top values" not in body
    assert "never cell values" in body
