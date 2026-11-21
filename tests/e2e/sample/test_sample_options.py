"""`decoy run --sample N` options and refusals (SAMPLE SC1: AT-C1, AT-C2, AT-C2a, AT-C3a).

Every refusal exits 1 with fixed text before any engine run; until SC2 lands the run branch, a
sample that passes them stops with one more refusal and leaves no scratch folder behind.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import csv_source

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    for name in ("DECOY_PROJECT", "DECOY_LIBRARY"):
        monkeypatch.delenv(name, raising=False)
    return folder


def _flat(text: str) -> str:
    return " ".join(text.split())


def _mask_pipeline(folder: Path, extra: dict | None = None) -> Path:
    src = folder / "people.csv"
    pd.DataFrame({"email": ["a@example.com", "b@example.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"people": csv_source(src)},
        "tables": [{"name": "people", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"people": {"type": "file", "format": "csv", "path": "people_out.csv"}},
        **(extra or {}),
    }
    path = folder / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    return root


def _files(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


@pytest.mark.parametrize("n", ["0", "1001", "-3"])
def test_a_size_outside_the_engine_range_exits_1_before_any_engine_run(
    tmp_path: Path, n: str
) -> None:
    root = _project(tmp_path)
    cfg = _mask_pipeline(root)
    before = _files(root)

    res = runner.invoke(app, ["run", str(cfg), "--sample", n])

    assert res.exit_code == 1, res.output
    assert "from 1 to 1000" in _flat(res.output)
    assert _files(root) == before


def test_a_non_integer_size_is_a_usage_error(tmp_path: Path) -> None:
    cfg = _mask_pipeline(_project(tmp_path))
    res = runner.invoke(app, ["run", str(cfg), "--sample", "many"])
    assert res.exit_code == 2


@pytest.mark.parametrize(
    "flag",
    [
        ["--rows", "5"],
        ["--chunked"],
        ["--chunk-size", "50"],
        ["--vault", "v.json"],
        ["--evidence-out", "e.json"],
        ["--notify", "email:ops@example.com"],
        ["--duckdb-source", "people=db.duckdb"],
        ["--out-dir", "elsewhere"],
    ],
)
def test_each_refused_flag_exits_1_with_its_own_text(tmp_path: Path, flag: list[str]) -> None:
    root = _project(tmp_path)
    cfg = _mask_pipeline(root)
    before = _files(root)

    res = runner.invoke(app, ["run", str(cfg), "--sample", "5", *flag])

    assert res.exit_code == 1, res.output
    assert f"--sample cannot run with {flag[0]}." in _flat(res.output)
    assert _files(root) == before


def test_sample_root_needs_sample(tmp_path: Path) -> None:
    cfg = _mask_pipeline(_project(tmp_path))
    res = runner.invoke(app, ["run", str(cfg), "--sample-root", "people"])
    assert res.exit_code == 1
    assert "--sample-root needs --sample." in _flat(res.output)


def test_sample_root_with_a_subset_block_needs_no_subset(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _mask_pipeline(root, {"subset": {"seeds": [{"table": "people", "rows": 1}]}})

    refused = runner.invoke(app, ["run", str(cfg), "--sample", "2", "--sample-root", "people"])
    assert refused.exit_code == 1
    assert "`subset:` block" in _flat(refused.output)

    allowed = runner.invoke(
        app, ["run", str(cfg), "--sample", "2", "--sample-root", "people", "--no-subset"]
    )
    assert "`subset:` block" not in _flat(allowed.output)


def _generated_parent_masked_child(folder: Path) -> Path:
    src = folder / "kids.csv"
    pd.DataFrame({"pid": [1, 2], "name": ["x", "y"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"kids": csv_source(src)},
        "tables": [
            {
                "name": "parents",
                "row_count": 10,
                "generate_columns": [{"name": "pid", "type": "sequence", "start": 1, "step": 1}],
            },
            {"name": "kids", "columns": [{"name": "name", "strategy": "redact"}]},
        ],
        "relationships": [
            {
                "parent": {"table": "parents", "columns": ["pid"]},
                "children": [{"table": "kids", "columns": ["pid"]}],
                "orphan_policy": "fail",
            }
        ],
        "targets": {
            "parents": {"type": "file", "format": "csv", "path": "parents.csv"},
            "kids": {"type": "file", "format": "csv", "path": "kids_out.csv"},
        },
    }
    path = folder / "edge.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_a_generated_parent_of_a_masked_child_is_refused_naming_only_tables_and_columns(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    cfg = _generated_parent_masked_child(root)
    before = _files(root)

    res = runner.invoke(app, ["run", str(cfg), "--sample", "5"])

    assert res.exit_code == 1, res.output
    text = _flat(res.output)
    assert "would orphan the masked child" in text
    assert "parents (pid)" in text and "kids (pid)" in text
    assert _files(root) == before  # no scratch folder, no target


def test_outside_a_project_exits_1_before_a_scratch_folder_or_engine_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli.library import _paths

    reached: list[str] = []
    real = _paths.resolve_root
    monkeypatch.setattr(_paths, "resolve_root", lambda **kw: (reached.append("x"), real(**kw))[1])
    work = tmp_path / "loose"
    work.mkdir()
    cfg = _mask_pipeline(work)
    before = _files(work)

    res = runner.invoke(app, ["run", str(cfg), "--sample", "5", "--json"])

    assert res.exit_code == 1, res.output
    assert "layout.project_not_found" in res.output
    assert "not available yet" not in res.output
    assert reached == []  # the library was never resolved: the refusal came first
    assert _files(work) == before  # no .decoy library, no scratch folder


def test_inside_a_project_the_scratch_comes_from_the_project_library_and_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    cfg = _mask_pipeline(root)
    from decoy.cli.library import _store

    real = _store.open_library
    roots: list[Path] = []

    def spy(path: Path, **kw):
        roots.append(path)
        return real(path, **kw)

    monkeypatch.setattr(_store, "open_library", spy)
    monkeypatch.setattr("decoy.cli.library.open_library", spy, raising=False)

    res = runner.invoke(app, ["run", str(cfg), "--sample", "5"])

    assert res.exit_code == 1, res.output
    assert "--sample is not available yet" in _flat(res.output)
    assert roots and roots[0] == root.resolve() / ".decoy"
    scratch = root / ".decoy" / "scratch"
    assert not scratch.exists() or not any(scratch.iterdir())
    assert not (root / "people_out.csv").exists() and not (root / "out").exists()


def _snapshot(folder: Path) -> dict[str, bytes | None]:
    return {
        str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(folder.rglob("*"))
    }


def test_an_external_decoy_library_never_receives_the_sample_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    cfg = _mask_pipeline(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"untouched")
    before = _snapshot(outside)
    monkeypatch.setenv("DECOY_LIBRARY", str(outside))
    from decoy.cli.library import _store

    real = _store.open_library
    roots: list[Path] = []

    def spy(path: Path, **kw):
        roots.append(path)
        return real(path, **kw)

    monkeypatch.setattr(_store, "open_library", spy)
    monkeypatch.setattr("decoy.cli.library.open_library", spy, raising=False)

    res = runner.invoke(app, ["run", str(cfg), "--sample", "5"])

    assert res.exit_code == 1, res.output
    assert "--sample is not available yet" in _flat(res.output)
    assert roots == [root.resolve() / ".decoy"]
    assert _snapshot(outside) == before
