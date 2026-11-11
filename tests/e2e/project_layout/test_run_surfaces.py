"""AT-8 and the `--out-dir` cells (P4): what `decoy run` says about where it wrote.

The summary prints the project, the run folder and the `current` link; `--json` adds
`output_dir`, `outputs` (`{table, path}` for files written only), `project` (`root`,
`implicit`, `skipped`) and `pipeline` (`name`, `yaml`, `given_as`), the shapes of plan 7.6.
Human paths are relative when under the current folder and absolute otherwise; `--json`
paths are always absolute. `--out-dir DIR` replaces the run folder: no claim, no run id, no `LATEST`, no
`out/.gitignore`, and a second run overwrites as before.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import _targets
from tests.csv_sources import csv_source

runner = CliRunner()
WIDE = {"COLUMNS": "1000"}
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    return root


def _pipeline(root: Path, target: str = "masked.csv") -> Path:
    src = root / "a.csv"
    emails = ["a@example.com", "b@example.com"]
    pd.DataFrame({"email": pd.Series(emails, dtype="string")}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": target}},
    }
    path = root / "pipelines" / "orders" / "pipeline.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _only_run(root: Path) -> Path:
    (run,) = [p for p in (root / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    return run


def _flat(text: str) -> str:
    return "".join(text.split())


def _json(result) -> dict:
    return json.loads(result.stdout)


def _paths(doc: dict) -> list[str]:
    return [entry["path"] for entry in doc["outputs"]]


# --- AT-8 --json -------------------------------------------------------------------------


def test_json_names_the_run_folder_outputs_project_and_pipeline(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_OK, result.output
    doc = _json(result)
    run = _only_run(root)
    assert doc["output_dir"] == str(run.resolve())
    assert doc["outputs"] == [{"table": "a", "path": str((run / "masked.csv").resolve())}]
    assert doc["project"] == {"root": str(root.resolve()), "implicit": False, "skipped": []}
    assert doc["pipeline"] == {"name": "orders", "yaml": str(cfg.resolve()), "given_as": "path"}


def test_an_empty_chunked_source_is_absent_from_outputs(tmp_path: Path, monkeypatch) -> None:
    # A source that yields no chunk at all: the chunked writer publishes nothing.
    from decoy.cli.run import _execute

    root = _project(tmp_path)
    cfg = _pipeline(root)
    monkeypatch.setattr(_execute, "iter_source_chunks", lambda *args, **kwargs: iter(()))
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--json"])
    assert result.exit_code == EXIT_OK, result.output
    doc = _json(result)
    assert doc["outputs"] == []
    assert doc["output_dir"] == str(_only_run(root).resolve())


def test_a_failure_after_a_write_names_the_run_folder(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    real = _targets.write_table

    def write_then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("disk went away")

    monkeypatch.setattr(_targets, "write_table", write_then_fail)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code != EXIT_OK
    doc = _json(result)
    assert doc["status"] == "error"
    run = _only_run(root)
    assert doc["output_dir"] == str(run.resolve())


def test_a_failure_before_any_write_names_no_removed_folder(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)

    def fail(*args, **kwargs):
        raise RuntimeError("disk went away")

    monkeypatch.setattr(_targets, "write_table", fail)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code != EXIT_OK
    doc = _json(result)
    assert "output_dir" not in doc
    assert not any(p.name[0].isdigit() for p in (root / "out" / "orders").iterdir())


def test_a_gate_refusal_has_no_output_dir(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root, "../../x.csv")
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "output_dir" not in _json(result)


def test_json_paths_are_absolute_even_under_the_current_folder(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    monkeypatch.chdir(root)
    doc = _json(runner.invoke(app, ["run", str(cfg.relative_to(root)), "--json"]))
    assert Path(doc["output_dir"]).is_absolute()
    assert Path(doc["project"]["root"]).is_absolute()
    assert Path(doc["pipeline"]["yaml"]).is_absolute()
    assert all(Path(p).is_absolute() for p in _paths(doc))


def test_json_for_absolute_targets_only_has_no_run_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    target = tmp_path / "delivery.csv"
    cfg = _pipeline(root, str(target))
    doc = _json(runner.invoke(app, ["run", str(cfg), "--json"]))
    assert doc["output_dir"] is None
    assert doc["project"] is None
    assert doc["pipeline"] is None
    assert doc["outputs"] == [{"table": "a", "path": str(target.resolve())}]


# --- AT-8 summary ------------------------------------------------------------------------


def test_the_summary_prints_project_run_folder_and_current_relative_under_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run", str(cfg.relative_to(root))], env=WIDE)
    assert result.exit_code == EXIT_OK, result.output
    out = _flat(result.output)
    run = _only_run(root)
    assert _flat("Project .") in out
    assert _flat(f"Run folder out/orders/{run.name}") in out
    assert _flat("Latest out/orders/current") in out
    assert str(root) not in result.output


def test_the_summary_prints_absolute_paths_outside_the_current_folder(
    tmp_path: Path, monkeypatch
) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(app, ["run", str(cfg)], env=WIDE)
    assert result.exit_code == EXIT_OK, result.output
    out = _flat(result.output)
    run = _only_run(root)
    assert _flat(f"Project {root.resolve()}") in out
    assert _flat(f"Run folder {run.resolve()}") in out
    assert _flat(f"Latest {root.resolve() / 'out' / 'orders' / 'current'}") in out


# --- --out-dir -----------------------------------------------------------------------------


def test_out_dir_replaces_the_run_folder(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", "build", "--json"])
    assert result.exit_code == EXIT_OK, result.output
    build = tmp_path / "build"
    assert (build / "masked.csv").is_file()
    assert sorted(p.name for p in build.iterdir()) == ["masked.csv"]
    assert not (root / "out").exists()
    doc = _json(result)
    assert doc["output_dir"] == str(build.resolve())
    assert _paths(doc) == [str((build / "masked.csv").resolve())]


@posix_only
def test_a_missing_out_dir_is_made_owner_only(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    build = tmp_path / "new" / "build"
    build.parent.mkdir()
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert stat.S_IMODE(build.stat().st_mode) == 0o700


def test_out_dir_overwrites_like_before(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root)
    build = tmp_path / "build"
    for _ in range(2):
        result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
        assert result.exit_code == EXIT_OK, result.output
    assert sorted(p.name for p in build.iterdir()) == ["masked.csv"]


def test_out_dir_keeps_an_absolute_target_at_its_path(tmp_path: Path) -> None:
    root = _project(tmp_path)
    target = tmp_path / "delivery.csv"
    cfg = _pipeline(root, str(target))
    build = tmp_path / "build"
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert target.is_file()
    assert not (build / "delivery.csv").exists()


def test_out_dir_places_nested_targets_inside_it(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _pipeline(root, "sub/masked.csv")
    build = tmp_path / "build"
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert (build / "sub" / "masked.csv").is_file()
