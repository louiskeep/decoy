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
    assert "outputs" not in doc
    assert "output_dir" not in doc


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
    assert "output_dir" not in doc
    assert doc["project"] is None
    assert doc["pipeline"] is None
    assert doc["outputs"] == [{"table": "a", "path": str(target.resolve())}]


# --- AT-32 the JSON location fields follow what was published --------------------------------


def _two_target_pipeline(root: Path, first: str, second: str) -> Path:
    path = _pipeline(root, first)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["sources"]["b"] = cfg["sources"]["a"]
    cfg["tables"].append({"name": "b", "columns": [{"name": "email", "strategy": "redact"}]})
    cfg["targets"]["b"] = {"type": "file", "format": "csv", "path": second}
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _fail_on_second_write(monkeypatch) -> None:
    real = _targets.write_table
    calls: list[int] = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("disk went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(_targets, "write_table", flaky)


def _fail_every_write(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("disk went away")

    monkeypatch.setattr(_targets, "write_table", fail)


@pytest.mark.parametrize(
    "cell",
    [
        "out_dir_gate_refusal",
        "placed_fails_before_publish",
        "fixed_fails_before_publish",
        "placed_fails_after_first_publish",
        "fixed_fails_after_first_publish",
        "absolute_fails_after_first_publish",
        "placed_success",
        "fixed_success",
        "empty_chunked_success",
        "absolute_only_success",
    ],
)
def test_json_location_fields_follow_publication(tmp_path: Path, monkeypatch, cell: str) -> None:
    from decoy.cli.run import _execute

    root = _project(tmp_path)
    build = tmp_path / "build"
    build.mkdir()
    extra: list[str] = []
    if cell == "out_dir_gate_refusal":
        cfg = _pipeline(root, "../../x.csv")
        extra = ["--out-dir", str(build)]
    elif cell.startswith("placed_fails_before"):
        cfg = _pipeline(root)
        _fail_every_write(monkeypatch)
    elif cell.startswith("fixed_fails_before"):
        cfg = _pipeline(root)
        extra = ["--out-dir", str(build)]
        _fail_every_write(monkeypatch)
    elif cell == "placed_fails_after_first_publish":
        cfg = _two_target_pipeline(root, "one.csv", "two.csv")
        _fail_on_second_write(monkeypatch)
    elif cell == "fixed_fails_after_first_publish":
        cfg = _two_target_pipeline(root, "one.csv", "two.csv")
        extra = ["--out-dir", str(build)]
        _fail_on_second_write(monkeypatch)
    elif cell == "absolute_fails_after_first_publish":
        cfg = _two_target_pipeline(root, str(tmp_path / "one.csv"), str(tmp_path / "two.csv"))
        _fail_on_second_write(monkeypatch)
    elif cell == "placed_success":
        cfg = _pipeline(root)
    elif cell == "fixed_success":
        cfg = _pipeline(root)
        extra = ["--out-dir", str(build)]
    elif cell == "empty_chunked_success":
        cfg = _pipeline(root)
        extra = ["--chunked"]
        monkeypatch.setattr(_execute, "iter_source_chunks", lambda *a, **k: iter(()))
    else:
        cfg = _pipeline(root, str(tmp_path / "delivery.csv"))
    result = runner.invoke(app, ["run", str(cfg), "--json", *extra])
    doc = _json(result)
    failed = "fails" in cell or "refusal" in cell
    assert (result.exit_code != EXIT_OK) is failed, result.output
    if cell in {
        "out_dir_gate_refusal",
        "placed_fails_before_publish",
        "fixed_fails_before_publish",
    }:
        expected: dict | None = None
    elif cell == "empty_chunked_success":
        expected = None
    elif cell.startswith("absolute"):
        names = ["one.csv", "two.csv"] if "fails" in cell else ["delivery.csv"]
        files = [str((tmp_path / n).resolve()) for n in names][:1]
        expected = {"outputs": files, "output_dir": None}
    else:
        folder = build.resolve() if cell.startswith("fixed") else _only_run(root).resolve()
        names = ["one.csv"] if "fails" in cell else ["masked.csv"]
        expected = {"outputs": [str(folder / n) for n in names], "output_dir": str(folder)}
    if expected is None:
        assert "outputs" not in doc
        assert "output_dir" not in doc
        return
    assert _paths(doc) == expected["outputs"]
    if expected["output_dir"] is None:
        assert "output_dir" not in doc
    else:
        assert doc["output_dir"] == expected["output_dir"]


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


@pytest.mark.parametrize("kind", ["missing_parent", "file"])
def test_an_invalid_out_dir_refuses_before_a_source_read(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    from decoy.cli.run import _execute

    root = _project(tmp_path)
    cfg = _pipeline(root)
    build = tmp_path / "missing" / "build" if kind == "missing_parent" else tmp_path / "build"
    if kind == "file":
        build.write_text("not a directory", encoding="utf-8")

    def unexpected(*_args, **_kwargs):
        pytest.fail("source was read before --out-dir validation")

    monkeypatch.setattr(_execute, "read_source", unexpected)
    monkeypatch.setattr(_execute, "iter_source_chunks", unexpected)
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "--out-dir" in result.output
    assert str(build) not in result.output


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
