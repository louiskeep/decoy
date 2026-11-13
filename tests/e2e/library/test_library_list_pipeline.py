"""`decoy library list --pipeline` takes a pipeline name or path (plan 4.15, ruling 2026-11-13).

The flag goes through the shared pipeline hooks (`pipeline_option`, `resolve_pipeline`), like every
other command that takes a pipeline, and filters on the resolved YAML's project-relative path,
the `pipeline` label a run's records carry (plan 4.3). ML-raw-flag (filter on the text as typed
instead of the resolved path) turns the name and subfolder cells red.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from decoy_engine import records
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import open_library
from tests.unit.library._helpers import INVOCATION, PRODUCER, envelope

runner = CliRunner()
CLAIMS = "pipelines/claims/pipeline.yaml"
MEMBERS = "pipelines/members/pipeline.yaml"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    for rel in (CLAIMS, MEMBERS):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text("version: 2\n", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return root


def _record(n: int, pipeline: str) -> records.RecordEnvelope:
    payload = json.loads(records.encode(envelope(n)))["payload"]
    return records.build(
        "sample-run", payload, producer=PRODUCER, invocation_id=INVOCATION,
        created_at=datetime(2026, 11, 10 + n, tzinfo=timezone.utc),
        labels={"pipeline": pipeline},
    )  # fmt: skip


@pytest.fixture
def stored(project: Path) -> dict[str, list[str]]:
    library = open_library(project / DECOY_DIR)
    claims = [library.put(_record(n, CLAIMS)).id for n in (1, 3)]
    members = [library.put(_record(2, MEMBERS)).id]
    return {CLAIMS: claims, MEMBERS: members}


def _listed(*args: str) -> list[str]:
    result = runner.invoke(app, ["library", "list", "--json", *args])
    assert result.exit_code == EXIT_OK, result.output
    return [r["id"] for r in json.loads(result.stdout)["records"]]


def test_without_the_flag_every_pipeline_is_listed(stored: dict[str, list[str]]) -> None:
    assert sorted(_listed()) == sorted(stored[CLAIMS] + stored[MEMBERS])  # non-vacuous control


def test_a_pipeline_name_lists_only_its_records(stored: dict[str, list[str]]) -> None:
    assert _listed("--pipeline", "claims") == stored[CLAIMS]


def test_a_pipeline_path_lists_only_its_records(stored: dict[str, list[str]]) -> None:
    assert _listed("--pipeline", MEMBERS) == stored[MEMBERS]


def test_a_path_typed_from_a_subfolder_resolves_to_the_same_pipeline(
    project: Path, stored: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = project / "notes"
    sub.mkdir()
    monkeypatch.chdir(sub)
    assert _listed("--pipeline", "../" + CLAIMS) == stored[CLAIMS]


def test_an_unknown_name_is_the_shared_hook_usage_error(stored: dict[str, list[str]]) -> None:
    result = runner.invoke(app, ["library", "list", "--json", "--pipeline", "nope"])
    assert result.exit_code == EXIT_USAGE
    doc: dict[str, Any] = json.loads(result.stdout)
    assert doc["command"] == "library list" and doc["code"] == "layout.pipeline_unknown"
    assert "claims" in doc["error"]  # non-vacuous: the shared hook listed the known pipelines
