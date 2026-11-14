"""AT-C13: `report fidelity` and `report integrity` with `--config` check the actual `--source`
against the selected table's declaration before reading it; `detokenize` checks its config
before it reads the tokenized file.

Fidelity picks the declared source whose path is `--source`, else the config's only table, else
refuses with fixed text. Integrity anchors on the first declared table. Without `--config` both
verbs keep the caller-named default (a header row) and run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import csv_source

runner = CliRunner()

_ALL = [{"name": n, "strategy": "passthrough"} for n in ("id", "name", "age")]
_PARTIAL = _ALL[:2]
_FRAME = pd.DataFrame({"id": ["1", "2"], "name": ["Alice", "Bob"], "age": ["31", "4"]})


def _pair(tmp_path: Path, *, header: bool = True) -> tuple[Path, Path]:
    src, out = tmp_path / "people.csv", tmp_path / "masked.csv"
    _FRAME.to_csv(src, index=False, header=header)
    _FRAME.to_csv(out, index=False)
    return src, out


def _config(tmp_path: Path, columns: list[dict[str, Any]], **extra: Any) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "sources": {"people": csv_source(tmp_path / "people.csv"), **extra.get("sources", {})},
        "tables": [{"name": "people", "columns": columns}, *extra.get("tables", [])],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}},
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


@pytest.fixture
def read_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import decoy.cli._sources as sources_mod

    calls: list[str] = []
    real = sources_mod.read_csv_frame

    def spy(*a, **k):
        calls.append("read")
        return real(*a, **k)

    monkeypatch.setattr(sources_mod, "read_csv_frame", spy)
    return calls


def test_fidelity_with_config_refuses_an_undeclared_column_before_any_read(
    tmp_path: Path, read_spy: list[str]
) -> None:
    src, out = _pair(tmp_path)
    cfg = _config(tmp_path, _PARTIAL)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out), "--config", str(cfg)])
    assert result.exit_code == 1
    assert "source_file.undeclared_column" in result.output
    assert str(tmp_path) not in result.output
    assert read_spy == []


def test_fidelity_checks_the_source_given_not_the_declared_path(
    tmp_path: Path, read_spy: list[str]
) -> None:
    # The declared file is fine; the file passed as --source has an extra column.
    _src, out = _pair(tmp_path)
    other = tmp_path / "other.csv"
    _FRAME.assign(extra="x").to_csv(other, index=False)
    cfg = _config(tmp_path, _ALL)
    result = runner.invoke(app, ["report", "fidelity", str(other), str(out), "--config", str(cfg)])
    assert result.exit_code == 1
    assert "source_file.undeclared_column" in result.output
    assert read_spy == []


def test_fidelity_with_declared_columns_runs(tmp_path: Path) -> None:
    src, out = _pair(tmp_path)
    cfg = _config(tmp_path, _ALL)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out), "--config", str(cfg)])
    assert result.exit_code == 0, result.output


def test_fidelity_without_config_keeps_the_caller_named_default(tmp_path: Path) -> None:
    src, out = _pair(tmp_path)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out)])
    assert result.exit_code == 0, result.output


def test_fidelity_several_tables_and_no_matching_source_is_a_usage_refusal(
    tmp_path: Path, read_spy: list[str]
) -> None:
    _src, out = _pair(tmp_path)
    other = tmp_path / "elsewhere.csv"
    _FRAME.to_csv(other, index=False)
    (tmp_path / "pets.csv").write_text("id\n1\n", encoding="utf-8")
    cfg = _config(
        tmp_path,
        _ALL,
        sources={"pets": csv_source(tmp_path / "pets.csv")},
        tables=[{"name": "pets", "columns": [{"name": "id", "strategy": "passthrough"}]}],
    )
    result = runner.invoke(app, ["report", "fidelity", str(other), str(out), "--config", str(cfg)])
    assert result.exit_code == 1
    assert "declares several tables" in result.output
    assert str(tmp_path) not in result.output
    assert read_spy == []


@pytest.mark.parametrize("flag", [[], ["--allow-source-mismatch"]])
def test_integrity_with_config_refuses_an_undeclared_column_before_any_read(
    flag: list[str], tmp_path: Path, read_spy: list[str]
) -> None:
    src, out = _pair(tmp_path)
    cfg = _config(tmp_path, _PARTIAL)
    result = runner.invoke(
        app, ["report", "integrity", str(out), "--source", str(src), "--config", str(cfg), *flag]
    )
    assert result.exit_code == 1
    assert "source_file.undeclared_column" in result.output
    assert read_spy == []


def test_integrity_without_config_runs(tmp_path: Path) -> None:
    src, out = _pair(tmp_path)
    result = runner.invoke(app, ["report", "integrity", str(out), "--source", str(src), "--json"])
    assert result.exit_code in (0, 4), result.output


def test_detokenize_refuses_an_undeclared_config_before_reading_the_tokenized_file(
    tmp_path: Path, read_spy: list[str]
) -> None:
    _src, out = _pair(tmp_path)
    cols = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "name", "strategy": "tokenize", "namespace": "ns"},
    ]
    cfg = _config(tmp_path, cols)
    result = runner.invoke(
        app, ["detokenize", str(cfg), str(out), "--vault", str(tmp_path / "v.db")]
    )
    assert result.exit_code == 1
    assert "source_file.undeclared_column" in result.output
    assert read_spy == []
