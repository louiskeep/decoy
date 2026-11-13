"""Target-path advisories for a first-time user (CLI-QA1 C3b, item 7).

An output folder does not exist yet on a first run and the writer creates it, so the old
"output directory does not exist" warning was false. The advisory covers absolute targets;
a relative target lands in a new run folder, so nothing it names beforehand can collide.
Each cell runs both routes: `validate preflight` and the gate's config layer.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.gate import run_config_gate

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qa_first_user"


def _stage(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    for name in ("patients.csv", "visits.csv", "pipeline_namespaced.yaml"):
        shutil.copy(_FIXTURES / name, project / name)
    return project / "pipeline_namespaced.yaml"


def _elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)


def _preflight_names(config: Path) -> set[str]:
    result = runner.invoke(app, ["validate", "preflight", str(config), "--json"])
    return {c["name"] for c in json.loads(result.stdout)["checks"]}


def _gate_codes(config: Path) -> set[str]:
    return {f.code for f in run_config_gate(config).findings}


def _target_codes(codes: set[str]) -> set[str]:
    return {c for c in codes if c.startswith("target.")}


def _set_targets(config: Path, **paths: str) -> None:
    import yaml

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    for table, target in paths.items():
        raw["targets"][table]["path"] = target
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")


def test_missing_out_folder_gives_no_warning_on_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    _set_targets(config, patients=str(tmp_path / "new" / "p.csv"))
    _elsewhere(tmp_path, monkeypatch)
    assert _target_codes(_preflight_names(config)) == set()
    assert _target_codes(_gate_codes(config)) == set()


def test_a_file_in_the_way_warns_unwritable_on_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    (tmp_path / "blocker").write_text("not a folder\n", encoding="utf-8")
    _set_targets(
        config,
        patients=str(tmp_path / "blocker" / "patients.csv"),
        visits=str(tmp_path / "blocker" / "visits.csv"),
    )
    _elsewhere(tmp_path, monkeypatch)
    expected = {"target.patients.parent_unwritable", "target.visits.parent_unwritable"}
    assert _target_codes(_preflight_names(config)) == expected
    assert _target_codes(_gate_codes(config)) == expected


def test_existing_absolute_target_warns_would_overwrite_on_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    existing = tmp_path / "done" / "patients.csv"
    existing.parent.mkdir()
    existing.write_text("x\n", encoding="utf-8")
    _set_targets(config, patients=str(existing), visits=str(existing.parent / "visits.csv"))
    _elsewhere(tmp_path, monkeypatch)
    assert _target_codes(_preflight_names(config)) == {"target.patients.would_overwrite"}
    assert _target_codes(_gate_codes(config)) == {"target.patients.would_overwrite"}


def test_relative_target_with_an_existing_file_gives_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative target lands in a new run folder, so the config-folder file is not overwritten."""
    config = _stage(tmp_path)
    (config.parent / "out").mkdir()
    (config.parent / "out" / "patients.csv").write_text("x\n", encoding="utf-8")
    _elsewhere(tmp_path, monkeypatch)
    assert _target_codes(_preflight_names(config)) == set()
    assert _target_codes(_gate_codes(config)) == set()


@pytest.mark.parametrize("route", [["validate", "preflight"], ["validate"]])
def test_invalid_target_path_is_a_value_free_json_warning(tmp_path: Path, route: list[str]) -> None:
    config = _stage(tmp_path)
    # A NUL byte is refused earlier by the layout gate; an over-long name reaches this check.
    # The second target shares the folder, so the one-root rule has nothing to refuse.
    _set_targets(
        config,
        patients=str(tmp_path / ("zz_marker_" + "a" * 300)) + ".csv",
        visits=str(tmp_path / "visits.csv"),
    )

    result = runner.invoke(app, [*route, str(config), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    rows = payload["checks"] if "checks" in payload else payload["messages"]
    warning = next(row for row in rows if row.get("code", row.get("name")).endswith("path_invalid"))
    assert warning["message"] == "Output target path for table patients is invalid."
    assert "zz_marker_" not in result.stdout


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX non-root permissions")
def test_non_writable_target_directory_warns_on_both_routes(tmp_path: Path) -> None:
    config = _stage(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert not os.access(locked, os.W_OK | os.X_OK)
        _set_targets(
            config, patients=str(locked / "patients.csv"), visits=str(locked / "visits.csv")
        )
        expected = {"target.patients.parent_unwritable", "target.visits.parent_unwritable"}
        assert _target_codes(_preflight_names(config)) == expected
        assert _target_codes(_gate_codes(config)) == expected
    finally:
        locked.chmod(0o700)
