"""AT-29 (P9): `report integrity` and `report fidelity` write into the run folder by default.

With no output flag and the checked file inside a run folder, the JSON report is also written to
`<run>/reports/<kind>.json` and its path is printed. A typed flag wins and is the only file
written. A file outside any run folder writes nothing new.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK
from tests.csv_sources import csv_source

runner = CliRunner()
WIDE = {"COLUMNS": "1000"}


def _masked_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "proj"
    (root / "pipelines" / "orders").mkdir(parents=True)
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    src = root / "a.csv"
    pd.DataFrame({"email": pd.Series(["a@example.com", "b@example.com"], dtype="string")}).to_csv(
        src, index=False
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    (root / "pipelines" / "orders" / "pipeline.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )
    result = runner.invoke(app, ["run", str(root / "pipelines" / "orders" / "pipeline.yaml")])
    assert result.exit_code == EXIT_OK, result.output
    (run,) = [p for p in (root / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    return root, src, run / "masked.csv"


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _integrity(masked: Path, src: Path, *extra: str):
    return runner.invoke(
        app, ["report", "integrity", str(masked), "--source", str(src), *extra], env=WIDE
    )


def _fidelity(src: Path, masked: Path, *extra: str):
    return runner.invoke(app, ["report", "fidelity", str(src), str(masked), *extra], env=WIDE)


@pytest.mark.parametrize("kind", ["integrity", "fidelity"])
def test_a_run_output_gets_a_report_in_its_run_folder(tmp_path: Path, kind: str) -> None:
    _root, src, masked = _masked_run(tmp_path)
    result = _integrity(masked, src) if kind == "integrity" else _fidelity(src, masked)
    assert result.exit_code in (EXIT_OK, 4), result.output
    report = masked.parent / "reports" / f"{kind}.json"
    assert json.loads(report.read_text(encoding="utf-8"))
    assert (
        str(report) in result.output or report.relative_to(Path.cwd()).as_posix() in result.output
    )
    if sys.platform != "win32":
        assert (report.parent.stat().st_mode & 0o077) == 0
        assert (report.stat().st_mode & 0o077) == 0
    assert "a@example.com" not in report.read_text(encoding="utf-8")


def test_a_typed_flag_wins_and_is_the_only_file(tmp_path: Path) -> None:
    root, src, masked = _masked_run(tmp_path)
    typed = tmp_path / "typed.json"
    before = _files(root)
    assert _integrity(masked, src, "--output", str(typed)).exit_code in (EXIT_OK, 4)
    assert typed.is_file()
    assert _files(root) == before
    typed_f = tmp_path / "typed-f.json"
    assert _fidelity(src, masked, "--report-out", str(typed_f)).exit_code in (EXIT_OK, 4)
    assert typed_f.is_file()
    assert _files(root) == before


@pytest.mark.parametrize("kind", ["integrity", "fidelity"])
def test_a_file_outside_any_run_folder_writes_nothing(tmp_path: Path, kind: str) -> None:
    root, src, masked = _masked_run(tmp_path)
    loose = root / "loose.csv"
    loose.write_bytes(masked.read_bytes())
    before = _files(root)
    result = _integrity(loose, src) if kind == "integrity" else _fidelity(src, loose)
    assert result.exit_code in (EXIT_OK, 4), result.output
    assert _files(root) == before


@pytest.mark.parametrize("kind", ["integrity", "fidelity"])
def test_json_stdout_stays_one_document_and_names_the_default_report(
    tmp_path: Path, kind: str
) -> None:
    _root, src, masked = _masked_run(tmp_path)
    args = ("--json",)
    result = (
        _integrity(masked, src, *args) if kind == "integrity" else _fidelity(src, masked, *args)
    )
    assert result.exit_code in (EXIT_OK, 4), result.output
    doc = json.loads(result.stdout)
    written = masked.parent / "reports" / f"{kind}.json"
    assert Path(doc["report_path"]).samefile(written)
    typed = tmp_path / "t.json"
    flag = "--output" if kind == "integrity" else "--report-out"
    more = (*args, flag, str(typed))
    result = (
        _integrity(masked, src, *more) if kind == "integrity" else _fidelity(src, masked, *more)
    )
    assert "report_path" not in json.loads(result.stdout)


def test_quiet_prints_nothing_for_a_default_report(tmp_path: Path) -> None:
    _root, src, masked = _masked_run(tmp_path)
    result = _integrity(masked, src, "--quiet")
    assert (masked.parent / "reports" / "integrity.json").is_file()
    assert "Report" not in result.output


def test_report_under_config_by_name_and_by_path(tmp_path: Path, monkeypatch) -> None:
    root, src, masked = _masked_run(tmp_path)
    yaml_path = root / "pipelines" / "orders" / "pipeline.yaml"
    report = masked.parent / "reports" / "integrity.json"
    for config in (str(yaml_path), "orders"):
        report.unlink(missing_ok=True)
        monkeypatch.chdir(root)
        result = _integrity(masked, src, "--config", config)
        assert result.exit_code in (EXIT_OK, 4), result.output
        assert report.is_file()


# --- M1: a default report that cannot be written never changes the check's exit ------------


def _baseline_exit(masked: Path, src: Path) -> int:
    return _integrity(masked, src, "--output", str(masked.parent.parent / "base.json")).exit_code


def test_a_reports_folder_that_cannot_be_made_warns_and_keeps_the_exit(tmp_path: Path) -> None:
    _root, src, masked = _masked_run(tmp_path)
    expected = _baseline_exit(masked, src)
    (masked.parent / "reports").write_text("in the way", encoding="utf-8")
    expected_fidelity = _fidelity(src, masked, "--report-out", str(tmp_path / "f.json")).exit_code
    for result, want in (
        (_integrity(masked, src), expected),
        (_fidelity(src, masked), expected_fidelity),
    ):
        assert result.exit_code == want, result.output
        assert "layout.report_not_written" in result.output
        assert str(masked.parent) not in result.output


def test_a_failed_default_write_warns_and_a_typed_one_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy import _atomic
    from decoy.cli import report as report_module

    _root, src, masked = _masked_run(tmp_path)
    expected = _baseline_exit(masked, src)

    def boom(*_a: object, **_k: object) -> None:
        raise _atomic.AtomicWriteError(_atomic.ATOMIC_WRITE_FAILED)

    monkeypatch.setattr(report_module, "write_local_target", boom)
    result = _integrity(masked, src)
    assert result.exit_code == expected
    assert "layout.report_not_written" in result.output
    assert str(masked.parent) not in result.output
    typed = _integrity(masked, src, "--output", str(tmp_path / "t.json"))
    assert typed.exit_code == 1


# --- M2: a project with no marker ----------------------------------------------------------


def test_a_no_marker_project_still_gets_its_default_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "plain"
    d.mkdir()
    src = d / "s.csv"
    pd.DataFrame({"email": pd.Series(["a@example.com"], dtype="string")}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "m.csv"}},
    }
    (d / "p.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.chdir(d)
    assert runner.invoke(app, ["run", "p.yaml"]).exit_code == EXIT_OK
    (run,) = [p for p in (d / "out" / "p").iterdir() if p.is_dir() and p.name[0].isdigit()]
    result = _integrity(run / "m.csv", src)
    assert result.exit_code in (EXIT_OK, 4), result.output
    assert (run / "reports" / "integrity.json").is_file()
    stray = d / "stray" / "out" / "p" / run.name
    stray.mkdir(parents=True)
    (stray / "m.csv").write_bytes((run / "m.csv").read_bytes())
    _integrity(stray / "m.csv", src)
    assert not (stray / "reports").exists()


# --- V1-1: only a run folder its pipeline claim vouches for gets a default report ----------


def _look_alike(base: Path, masked: Path, name: str = "ghost") -> Path:
    """A copy of `masked` under `<base>/out/<name>/<run-id>/`, with no claim."""
    run = base / "out" / name / "20261109T101500123456Z-0a1b2c3d"
    run.mkdir(parents=True)
    (run / "m.csv").write_bytes(masked.read_bytes())
    return run


def _claims(root: Path, kind: str) -> str | None:
    return {
        "missing": None,
        "bogus": "pipelines/nothing/pipeline.yaml",
        "other": "pipelines/orders/pipeline.yaml",
    }[kind]


@pytest.mark.parametrize("claim", ["missing", "bogus", "other"])
@pytest.mark.parametrize("marker", [True, False])
def test_a_look_alike_run_folder_gets_no_report(tmp_path: Path, marker: bool, claim: str) -> None:
    root, src, masked = _masked_run(tmp_path)
    if marker:
        base = root
    else:
        base = tmp_path / "plain"
        base.mkdir()
    expected = _baseline_exit(masked, src)
    run = _look_alike(base, masked)
    text = _claims(root, claim)
    if text is not None:
        (run.parent / "PIPELINE").write_text(text + "\n", encoding="utf-8")
    before = _files(tmp_path)
    result = _integrity(run / "m.csv", src)
    assert result.exit_code == expected, result.output
    assert _files(tmp_path) == before
    fidelity = _fidelity(src, run / "m.csv")
    assert fidelity.exit_code in (EXIT_OK, 4)
    assert _files(tmp_path) == before


def test_a_claim_that_is_a_link_is_not_vouching(tmp_path: Path) -> None:
    root, src, masked = _masked_run(tmp_path)
    run = _look_alike(root, masked)
    real = masked.parent.parent / "PIPELINE"
    assert real.is_file()
    (run.parent / "PIPELINE").symlink_to(real)
    before = _files(tmp_path)
    _integrity(run / "m.csv", src)
    assert _files(tmp_path) == before
