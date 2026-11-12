"""Target-path advisories for a first-time user (CLI-QA1 C3b, item 7).

`out/` does not exist yet on a first run and the writer creates it, so the old
"output directory does not exist" warning was false. The check also looked for the target
under the process cwd while the writer uses the config's directory. Each cell runs both
routes: `validate preflight` and the gate's config layer.
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


def _set_patient_target(config: Path, target: str) -> None:
    import yaml

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["targets"]["patients"]["path"] = target
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")


def test_missing_out_folder_gives_no_warning_on_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    _elsewhere(tmp_path, monkeypatch)
    assert _target_codes(_preflight_names(config)) == set()
    assert _target_codes(_gate_codes(config)) == set()


def test_a_file_named_out_warns_unwritable_on_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    (config.parent / "out").write_text("not a folder\n", encoding="utf-8")
    _elsewhere(tmp_path, monkeypatch)
    expected = {"target.patients.parent_unwritable", "target.visits.parent_unwritable"}
    assert _target_codes(_preflight_names(config)) == expected
    assert _target_codes(_gate_codes(config)) == expected


def test_existing_target_is_found_relative_to_the_config_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _stage(tmp_path)
    (config.parent / "out").mkdir()
    (config.parent / "out" / "patients.csv").write_text("x\n", encoding="utf-8")
    _elsewhere(tmp_path, monkeypatch)
    assert _target_codes(_preflight_names(config)) == {"target.patients.would_overwrite"}
    assert _target_codes(_gate_codes(config)) == {"target.patients.would_overwrite"}


def test_a_stray_out_file_in_the_cwd_does_not_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: resolve the target with `Path(raw)` again and the cwd file warns."""
    config = _stage(tmp_path)
    _elsewhere(tmp_path, monkeypatch)
    (Path.cwd() / "out").mkdir()
    (Path.cwd() / "out" / "patients.csv").write_text("x\n", encoding="utf-8")
    assert _target_codes(_preflight_names(config)) == set()
    assert _target_codes(_gate_codes(config)) == set()


@pytest.mark.parametrize("route", [["validate", "preflight"], ["validate"]])
def test_invalid_target_path_is_a_value_free_json_warning(tmp_path: Path, route: list[str]) -> None:
    config = _stage(tmp_path)
    _set_patient_target(config, "missing/a\0b.csv")

    result = runner.invoke(app, [*route, str(config), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    rows = payload["checks"] if "checks" in payload else payload["messages"]
    warning = next(row for row in rows if row.get("code", row.get("name")).endswith("path_invalid"))
    assert warning["message"] == "Output target path for table patients is invalid."
    assert "missing/a" not in result.stdout


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX non-root permissions")
def test_non_writable_target_directory_warns_on_both_routes(tmp_path: Path) -> None:
    config = _stage(tmp_path)
    locked = config.parent / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert not os.access(locked, os.W_OK | os.X_OK)
        _set_patient_target(config, "locked/patients.csv")
        expected = {"target.patients.parent_unwritable"}
        assert _target_codes(_preflight_names(config)) == expected
        assert _target_codes(_gate_codes(config)) == expected
    finally:
        locked.chmod(0o700)
