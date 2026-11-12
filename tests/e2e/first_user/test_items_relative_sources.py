"""A relative source path reads from the config's folder on every command (GEN-CLI C1).

The engine opens a declared source as written, so each command that hands it a config must hand
it absolute source paths. Each test runs from a folder that holds no source file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF
from tests.run_outputs import latest_output

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()


@pytest.fixture
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A config folder `a` with a relative source, and a working directory `b` without one."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    pd.DataFrame({"id": [1, 2, 3], "email": ["x@e.com", "y@e.com", "z@e.com"]}).to_csv(
        a / "people.csv", index=False
    )
    monkeypatch.chdir(b)
    return a, b


def _config(a: Path, columns: list[dict]) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source("people.csv")},
        "tables": [{"name": "people", "columns": columns}],
        "targets": {"people": {"type": "file", "format": "csv", "path": "out.csv"}},
    }
    path = a / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


_MASK = [{"name": "email", "strategy": "redact"}]
_TOKEN = [{"name": "email", "strategy": "tokenize", "namespace": "people.email"}]


def test_run(elsewhere: tuple[Path, Path]) -> None:
    a, _b = elsewhere
    res = runner.invoke(app, ["run", str(_config(a, _MASK))])
    assert res.exit_code == 0, res.output
    assert latest_output(a, "out.csv").is_file()


def test_tokenize(elsewhere: tuple[Path, Path]) -> None:
    a, _b = elsewhere
    res = runner.invoke(app, ["tokenize", str(_config(a, _TOKEN)), "--vault", str(a / "t.db")])
    assert res.exit_code == 0, res.output
    assert latest_output(a, "out.csv").is_file()


@pytest.mark.parametrize(
    "argv",
    [
        ["validate", "config"],
        ["validate", "compile"],
        ["validate", "compile", "--explain"],
        ["validate", "preflight"],
        ["validate"],
    ],
)
def test_validate_commands(elsewhere: tuple[Path, Path], argv: list[str]) -> None:
    a, _b = elsewhere
    res = runner.invoke(app, [*argv, str(_config(a, _MASK))])
    assert res.exit_code == 0, (argv, res.output)


def test_ci_check(elsewhere: tuple[Path, Path]) -> None:
    from tests.ci_support import ci_manifest

    a, _b = elsewhere
    _config(a, _MASK)
    manifest = a / ".decoy-ci.yaml"
    manifest.write_text(ci_manifest(), encoding="utf-8")
    res = runner.invoke(app, ["ci", "check", str(manifest)])
    assert res.exit_code == 0, res.output


def test_demo_runs_from_any_folder(elsewhere: tuple[Path, Path]) -> None:
    res = runner.invoke(app, ["demo"])
    assert res.exit_code == 0, res.output
