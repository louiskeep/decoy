"""Every csv source the CLI builds itself states `has_header`.

Engine #409 made `has_header` required: `resolve_csv_dialect` and `FileSource` both refuse a
csv descriptor without it. The report verbs, `read_file`, `decoy init`, `decoy demo`, the
`mask()` API and the bundled templates all build csv descriptors of their own, so each one
is checked here. The key-presence checks hold on any engine; the reads fail on engine main
when a builder drops the key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from decoy.cli._sources import csv_file_source, read_file, read_report_source


def _csv_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in (config.get("sources") or {}).values() if s.get("format") == "csv"]


def test_csv_file_source_states_has_header() -> None:
    assert csv_file_source("a.csv") == {
        "type": "file",
        "format": "csv",
        "path": "a.csv",
        "has_header": True,
    }
    assert csv_file_source("a.tsv", delimiter="\t")["delimiter"] == "\t"
    assert csv_file_source("a.csv", has_header=False)["has_header"] is False


def test_undeclared_csv_reads_take_the_header_row(tmp_path: Path) -> None:
    path = tmp_path / "plain.csv"
    path.write_text("id,name\n1,Ana\n2,Bo\n", encoding="utf-8")

    report = read_report_source(path, {}, tmp_path)
    whole = read_file(path, "csv", None, table="plain")

    assert list(report.columns) == ["id", "name"]
    assert report["id"].tolist() == [1, 2]
    assert list(whole.columns) == ["id", "name"]
    assert whole["id"].tolist() == ["1", "2"]


@pytest.mark.parametrize("name", ["gdpr", "hipaa", "minimal", "pci"])
def test_bundled_template_csv_sources_state_has_header(name: str) -> None:
    from decoy.templates import get_template

    sources = _csv_sources(yaml.safe_load(get_template(name).body))
    assert sources
    assert all(s.get("has_header") is True for s in sources)


@pytest.mark.parametrize("suffix", [".csv", ".tsv"])
def test_init_scaffold_source_states_has_header(tmp_path: Path, suffix: str) -> None:
    from decoy.cli.init import _scaffold_source

    assert _scaffold_source(tmp_path / f"in{suffix}")["has_header"] is True


def test_demo_pipeline_csv_source_states_has_header(tmp_path: Path) -> None:
    from decoy.cli.demo import _build_pipeline_yaml

    config = yaml.safe_load(_build_pipeline_yaml(tmp_path / "in.csv", tmp_path / "out.csv"))
    sources = _csv_sources(config)
    assert sources
    assert all(s.get("has_header") is True for s in sources)


def test_api_path_source_states_has_header(tmp_path: Path) -> None:
    from decoy.api import _stage_source_entry

    assert _stage_source_entry("t", tmp_path / "a.csv", [], None)["has_header"] is True


@pytest.mark.parametrize("delimiter", [None, "\t"])
def test_init_scaffold_yaml_states_has_header(tmp_path: Path, delimiter: str | None) -> None:
    from decoy.cli._init_inference import Inference
    from decoy.cli.init import _build_scaffold_yaml

    body = _build_scaffold_yaml(
        input_path=tmp_path / "in.csv",
        output_path=tmp_path / "out.csv",
        column_names=["a"],
        inferences={"a": Inference(strategy="redact", review="redact a")},
        file_format="csv",
        delimiter=delimiter,
    )
    sources = _csv_sources(yaml.safe_load(body))
    assert sources
    assert all(s.get("has_header") is True for s in sources)
