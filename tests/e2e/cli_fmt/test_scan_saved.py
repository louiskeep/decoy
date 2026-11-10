"""Saved-scan readers (`scan fields`, `show`, `diff`) go through `load_scan_set` and accept the
`scan-set/v1` core and the bare legacy `profile.to_dict()`, from a path or from stdin."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.io import _scan_set

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scan" / "legacy_profile.json"
CANARY = "ZQCANARY"


@pytest.fixture
def legacy() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def legacy_file(tmp_path: Path, legacy: dict) -> Path:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    return path


def _people_csv(path: Path) -> Path:
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4", "C5"],
            "first_name": [f"{CANARY}{n}" for n in range(5)],
            "email": [f"zqcanary{n}@example.com" for n in range(5)],
            "ssn": ["111-22-3333", "222-33-4444", "333-44-5555", "444-55-6666", "555-66-7777"],
        }
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def core_file(tmp_path: Path) -> Path:
    out = tmp_path / "core.json"
    src = _people_csv(tmp_path / "people.csv")
    assert runner.invoke(app, ["scan", str(src), "--has-header", "-o", str(out)]).exit_code == 0
    return out


@pytest.fixture
def load_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every `load_scan_set` call the commands make."""
    import decoy.cli.scan as scan_mod

    calls: list[str] = []
    real = scan_mod.load_scan_set

    def spy(path: str) -> dict:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(scan_mod, "load_scan_set", spy)
    return calls


def test_the_fixture_meets_the_legacy_shape_check(legacy: dict) -> None:
    for key in _scan_set._LEGACY_TOP_REQUIRED:
        assert key in legacy
    for field in legacy["fields"]:
        for key in _scan_set._LEGACY_FIELD_REQUIRED:
            assert key in field
    assert CANARY in json.dumps(legacy["fields"][1]["top_values"])


# -- T2-load-bare -----------------------------------------------------------------------


def test_fields_show_and_diff_all_use_load_scan_set(core_file: Path, load_calls: list[str]) -> None:
    assert runner.invoke(app, ["scan", "fields", str(core_file)]).exit_code == 0
    assert runner.invoke(app, ["scan", "show", str(core_file), "ssn"]).exit_code == 0
    assert runner.invoke(app, ["scan", "diff", str(core_file), str(core_file)]).exit_code == 0
    assert load_calls == [str(core_file)] * 4


def test_a_core_file_lists_the_same_fields_as_the_scan(core_file: Path) -> None:
    result = runner.invoke(app, ["scan", "fields", str(core_file), "--json"])
    assert [f["name"] for f in json.loads(result.stdout)["fields"]] == [
        "customer_id",
        "first_name",
        "email",
        "ssn",
    ]


def test_a_multi_table_scan_needs_table(tmp_path: Path) -> None:
    a = _people_csv(tmp_path / "a.csv")
    b = _people_csv(tmp_path / "b.csv")
    out = tmp_path / "two.json"
    assert (
        runner.invoke(app, ["scan", str(a), str(b), "--has-header", "-o", str(out)]).exit_code == 0
    )
    bare = runner.invoke(app, ["scan", "fields", str(out)])
    assert bare.exit_code == 1 and "--table" in bare.output
    picked = runner.invoke(app, ["scan", "fields", str(out), "--table", "b"])
    assert picked.exit_code == 0
    missing = runner.invoke(app, ["scan", "fields", str(out), "--table", "zzz"])
    assert missing.exit_code == 1


# -- T2-schema-reject -------------------------------------------------------------------


def test_an_unknown_scan_schema_major_exits_1(core_file: Path, tmp_path: Path) -> None:
    doc = json.loads(core_file.read_text())
    doc["scan_schema"] = "scan-set/v2"
    bad = tmp_path / "v2.json"
    bad.write_text(json.dumps(doc))
    result = runner.invoke(app, ["scan", "fields", str(bad)])
    assert result.exit_code == 1
    assert "scan-set/v2" in result.output


def test_a_tag_that_could_hold_data_is_not_echoed(core_file: Path, tmp_path: Path) -> None:
    doc = json.loads(core_file.read_text())
    doc["scan_schema"] = f"{CANARY} secret value with spaces"
    bad = tmp_path / "odd.json"
    bad.write_text(json.dumps(doc))
    result = runner.invoke(app, ["scan", "fields", str(bad)])
    assert result.exit_code == 1 and CANARY not in result.output


# -- legacy -----------------------------------------------------------------------------


def test_legacy_fields_lists_every_field_and_no_canary(legacy_file: Path, legacy: dict) -> None:
    result = runner.invoke(app, ["scan", "fields", str(legacy_file), "--json"])
    assert result.exit_code == 0, result.output
    assert [f["name"] for f in json.loads(result.stdout)["fields"]] == [
        f["name"] for f in legacy["fields"]
    ]
    assert CANARY not in result.output


def test_legacy_show_reports_the_row_count_and_no_canary(legacy_file: Path) -> None:
    result = runner.invoke(app, ["scan", "show", str(legacy_file), "first_name", "--json"])
    assert result.exit_code == 0, result.output
    assert CANARY not in result.output
    card = runner.invoke(app, ["scan", "show", str(legacy_file), "first_name"])
    assert card.exit_code == 0 and CANARY not in card.output + card.stdout


def test_legacy_diff_against_a_core_scan_of_the_same_data(
    legacy_file: Path, core_file: Path, legacy: dict, tmp_path: Path
) -> None:
    same = json.loads(
        runner.invoke(app, ["scan", "diff", str(legacy_file), str(core_file), "--json"]).stdout
    )
    assert same["summary"]["added"] == 0 and same["summary"]["removed"] == 0
    trimmed = dict(legacy, fields=[f for f in legacy["fields"] if f["name"] != "ssn"])
    cut = tmp_path / "cut.json"
    cut.write_text(json.dumps(trimmed))
    diff = json.loads(
        runner.invoke(app, ["scan", "diff", str(legacy_file), str(cut), "--json"]).stdout
    )
    assert [r["name"] for r in diff["changes"]["removed"]] == ["ssn"]


@pytest.mark.parametrize(
    "doc",
    [
        {"row_count": 5},
        {"row_count": 5, "fields": "name"},
        {"row_count": "5", "fields": []},
        {"row_count": 5, "fields": [{"pii_score": 0.1}]},
        {"row_count": 5, "fields": [{"name": 3}]},
        {"unrelated": "value " + CANARY},
    ],
)
def test_a_dict_that_is_not_a_profile_exits_1_with_a_fixed_message(
    tmp_path: Path, doc: object
) -> None:
    path = tmp_path / "x.json"
    path.write_text(json.dumps(doc))
    result = runner.invoke(app, ["scan", "fields", str(path)])
    assert result.exit_code == 1
    assert "not a saved scan Decoy can read" in result.output
    assert CANARY not in result.output


# -- stdin ------------------------------------------------------------------------------


def test_stdin_legacy_matches_the_file(legacy_file: Path) -> None:
    text = legacy_file.read_text()
    for args in (["fields", "-", "--json"], ["show", "-", "ssn", "--json"]):
        from_stdin = runner.invoke(app, ["scan", *args], input=text)
        file_args = [str(legacy_file) if a == "-" else a for a in args]
        from_file = runner.invoke(app, ["scan", *file_args])
        assert from_stdin.exit_code == 0 == from_file.exit_code
        want, got = json.loads(from_file.stdout), json.loads(from_stdin.stdout)
        assert {k: v for k, v in got.items() if k != "scan"} == {
            k: v for k, v in want.items() if k != "scan"
        }
    one = runner.invoke(app, ["scan", "diff", "-", str(legacy_file), "--json"], input=text)
    two = runner.invoke(app, ["scan", "diff", str(legacy_file), "-", "--json"], input=text)
    for r in (one, two):
        assert r.exit_code == 0 and json.loads(r.stdout)["drift"] is False


def test_stdin_core_matches_the_file(core_file: Path) -> None:
    text = core_file.read_text()
    piped = runner.invoke(app, ["scan", "fields", "-", "--json"], input=text)
    direct = runner.invoke(app, ["scan", "fields", str(core_file), "--json"])
    assert json.loads(piped.stdout)["fields"] == json.loads(direct.stdout)["fields"]
    for args in (["-", str(core_file)], [str(core_file), "-"]):
        r = runner.invoke(app, ["scan", "diff", *args, "--json"], input=text)
        assert r.exit_code == 0 and json.loads(r.stdout)["drift"] is False


def test_diff_with_both_operands_on_stdin_is_refused_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_read(_: str) -> dict:
        raise AssertionError("stdin was read")

    import decoy.cli.scan as scan_mod

    monkeypatch.setattr(scan_mod, "load_scan_set", no_read)
    result = runner.invoke(app, ["scan", "diff", "-", "-"], input="{}")
    assert result.exit_code == 1
    assert "only one of OLD or NEW" in result.output


def test_a_json_list_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2]")
    assert runner.invoke(app, ["scan", "fields", str(path)]).exit_code == 1


def test_a_legacy_file_is_a_one_table_set_named_from_its_source_label(legacy_file: Path) -> None:
    named = runner.invoke(app, ["scan", "fields", str(legacy_file), "--table", "people"])
    assert named.exit_code == 0, named.output
    other = runner.invoke(app, ["scan", "fields", str(legacy_file), "--table", "table"])
    assert other.exit_code == 1
