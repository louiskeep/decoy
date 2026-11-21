"""`decoy run` stores its evidence record in the library by default (LIB L3a, evidence half).

Plan 4.16: a run writes its evidence record unless `--no-library` or `DECOY_LIBRARY=off`; 4.17: a
library that cannot be written warns and keeps the run's exit code. The manifest is built once
and stored as built (amendment 2026-11-12), so the record payload equals the `--evidence-out`
file. Until RESULT C1a and C1b land, `cli/run/_evidence.py` is the one caller of the library's
`store_evidence` (`tests/sentry/io_policy/test_library_writer.py` holds "exactly one caller").
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import open_library
from tests.csv_sources import csv_source

runner = CliRunner()
PIPELINE = "pipelines/customers.yaml"


def write_pipeline(root: Path, rel: str = PIPELINE, cells: tuple[str, ...] = ("a", "b")) -> Path:
    """A mask pipeline in `root` whose source and target sit beside the YAML."""
    yaml_path = root / rel
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    src = yaml_path.parent / "input.csv"
    pd.DataFrame(
        {"customer_id": [f"C{n}-{c}" for n, c in enumerate(cells)], "email": list(cells)}
    ).to_csv(src, index=False)
    config = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"customers": csv_source(src)},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "customer_id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "faker", "provider": "person_email"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": "masked.csv"},
        },
    }
    yaml_path.write_text(yaml.dump(config), encoding="utf-8")
    return yaml_path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()  # bounds the project walk
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    write_pipeline(root)
    monkeypatch.chdir(root)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return root


def _run(*args: str, env: dict[str, str] | None = None) -> object:
    return runner.invoke(app, ["run", PIPELINE, "--mode", "mask", *args], env=env)


def _evidence_rows(root: Path) -> list:
    if not (root / DECOY_DIR / "library").exists():
        return []
    return open_library(root / DECOY_DIR).rows(kind="evidence")


def test_a_run_stores_one_evidence_record_by_default(project: Path) -> None:
    result = _run("--json")
    assert result.exit_code == EXIT_OK, result.output
    out = json.loads(result.stdout)
    rows = _evidence_rows(project)
    assert len(rows) == 1
    row = rows[0]
    # The run-result record (second half of L3a) adds its own id after the evidence's.
    assert {k: v for k, v in out["library"].items() if k != "result"} == {
        "status": "stored",
        "root": str((project / DECOY_DIR).resolve()),
        "evidence": row.id,
    }
    record = open_library(project / DECOY_DIR).get(row.id)
    assert record.raw["invocation_id"] == record.raw["payload"]["run_id"]
    assert row.pipeline == PIPELINE  # the project-relative YAML path, as `list --pipeline` reads
    assert list(row.tables) == ["customers"]
    assert record.raw["links"] == []  # evidence links to nothing; the run-result links to it


def test_the_human_card_names_the_record_and_the_root(project: Path) -> None:
    result = _run()
    assert result.exit_code == EXIT_OK, result.output
    (row,) = _evidence_rows(project)
    assert row.id[7:19] in result.output and "Library" in result.output


@pytest.mark.parametrize("marker", [True, False], ids=["project", "no-marker"])
def test_the_record_payload_equals_the_evidence_out_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: bool
) -> None:
    """L3-evidence-same: built once, stored as built (no path rewritten, either way)."""
    root = tmp_path / "work"
    root.mkdir()
    (root / ".git").mkdir()
    if marker:
        (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    write_pipeline(root)
    monkeypatch.chdir(root)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    result = _run("--evidence-out", "ev.json")
    assert result.exit_code == EXIT_OK, result.output
    library_root = root / DECOY_DIR if marker else root / "pipelines" / DECOY_DIR
    (row,) = _evidence_rows(library_root.parent)
    stored = open_library(library_root).get(row.id).raw["payload"]
    assert stored == json.loads((root / "ev.json").read_text(encoding="utf-8"))
    assert ("path_base" in stored) is marker


@pytest.mark.parametrize("how", ["flag", "env"])
def test_no_library_or_env_off_stores_nothing(project: Path, how: str) -> None:
    args = ("--json", "--no-library") if how == "flag" else ("--json",)
    env = {"DECOY_LIBRARY": "off"} if how == "env" else None
    result = _run(*args, env=env)
    assert result.exit_code == EXIT_OK, result.output
    assert json.loads(result.stdout)["library"] == {"status": "skipped"}
    assert not (project / DECOY_DIR / "library").exists()


def test_a_library_that_cannot_be_written_warns_and_keeps_the_exit_code(project: Path) -> None:
    """L3-readonly (4.17), made with a file where the root folder goes: it fails as root too."""
    (project / DECOY_DIR).write_text("not a folder", encoding="utf-8")
    result = _run("--json")
    assert result.exit_code == EXIT_OK, result.output
    out = json.loads(result.stdout)
    library = out["library"]
    assert library["status"] == "failed" and library["code"]
    warnings = [line for line in result.stderr.splitlines() if "warning" in line]
    assert len(warnings) == 1 and library["code"] in warnings[0]
    assert all(Path(o["path"]).exists() for o in out["outputs"]) and out["outputs"]  # delivered


def test_a_run_that_fails_stores_no_evidence(project: Path) -> None:
    (project / "pipelines" / "input.csv").unlink()
    result = _run()
    assert result.exit_code != EXIT_OK
    assert _evidence_rows(project) == []


def test_a_preview_stores_no_evidence(project: Path) -> None:
    gen = project / "gen.yaml"
    gen.write_text(
        yaml.dump(
            {
                "version": 2,
                "global_settings": {"seed": 1},
                "tables": [
                    {
                        "name": "t",
                        "row_count": 5,
                        "generate_columns": [
                            {"name": "n", "type": "sequence", "start": 1, "step": 1}
                        ],
                    }
                ],
                "targets": {"t": {"type": "file", "format": "csv", "path": "t.csv"}},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["run", str(gen), "--rows", "2"])
    assert result.exit_code == EXIT_OK, result.output
    assert _evidence_rows(project) == []


def test_an_out_of_core_fk_run_stores_its_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The freeze snapshot's two-table FK mask run: it must store its record, not warn."""
    from tests.e2e.release_freeze.write_shapes import SECRET_ENV, build_workspace

    (tmp_path / ".git").mkdir()
    build_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    monkeypatch.setenv(SECRET_ENV, "ab" * 32)
    result = runner.invoke(
        app, ["run", "pipeline.yaml", "--mask-secret", f"env:{SECRET_ENV}", "--json"]
    )
    assert result.exit_code == EXIT_OK, result.output
    assert json.loads(result.stdout)["library"]["status"] == "stored"
