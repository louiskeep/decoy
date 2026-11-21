"""`decoy run` stores its run-result record in the library (LIB L3a, run-result half).

The record holds the document `cli/run/_result.py` built, once, so its payload is the `result`
member of `--json` (L3-payload-from-finish). On a successful run it links one way to the
evidence record stored a moment earlier (L3-records); a run that fails still stores the document,
with no evidence (L3-failed-run). The log link (L5b) and `report ... <id>` are not in this part.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import open_library
from tests.e2e.library.test_run_evidence_records import (
    PIPELINE,
    _run,
    project,  # noqa: F401  (fixture)
)

CANONICAL = dict(sort_keys=True, separators=(",", ":"))


def _rows(root: Path, kind: str) -> list:
    if not (root / DECOY_DIR / "library").exists():
        return []
    return open_library(root / DECOY_DIR).rows(kind=kind)


def _stored(root: Path, row_id: str) -> dict:
    return open_library(root / DECOY_DIR).get(row_id).raw


def test_a_run_stores_a_result_record_that_links_to_its_evidence(project: Path) -> None:  # noqa: F811
    result = _run("--json")
    assert result.exit_code == EXIT_OK, result.output
    out = json.loads(result.stdout)
    (evidence,) = _rows(project, "evidence")
    (row,) = _rows(project, "run-result")
    assert out["library"] == {
        "status": "stored",
        "root": str((project / DECOY_DIR).resolve()),
        "evidence": evidence.id,
        "result": row.id,
    }
    raw = _stored(project, row.id)
    assert raw["invocation_id"] == _stored(project, evidence.id)["invocation_id"]
    assert raw["links"] == [{"rel": "evidence", "id": evidence.id}]
    assert _stored(project, evidence.id)["links"] == []  # one way: evidence links to nothing
    assert row.pipeline == PIPELINE and list(row.tables) == ["customers"]
    assert row.status == "succeeded"
    assert _stored(project, row.id)["payload"]["exit_code"] == 0


def test_the_index_finds_the_result_from_the_evidence(project: Path) -> None:  # noqa: F811
    """The reverse direction is a query over the index's links (plan 4.3), never a stored link."""
    assert _run().exit_code == EXIT_OK
    (evidence,) = _rows(project, "evidence")
    rows = open_library(project / DECOY_DIR).rows()
    pointing = [r.id for r in rows if ("evidence", evidence.id) in r.links]
    assert pointing == [_rows(project, "run-result")[0].id]


def test_the_stored_payload_is_the_result_member_of_json(project: Path) -> None:  # noqa: F811
    """L3-payload-from-finish, on a success."""
    result = _run("--json")
    out = json.loads(result.stdout)
    (row,) = _rows(project, "run-result")
    stored = _stored(project, row.id)["payload"]
    assert json.dumps(stored, **CANONICAL) == json.dumps(out["result"], **CANONICAL)


def test_a_failed_run_stores_a_failed_result_and_no_evidence(project: Path) -> None:  # noqa: F811
    """L3-failed-run, and L3-payload-from-finish on a runtime failure (exit 3)."""
    with mock.patch("decoy_engine.run_pipeline", side_effect=RuntimeError("boom")):
        result = _run("--json")
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert _rows(project, "evidence") == []
    (row,) = _rows(project, "run-result")
    stored = _stored(project, row.id)
    payload = stored["payload"]
    assert payload["status"] == "failed" and payload["exit_code"] == EXIT_RUNTIME
    assert payload["failure"]["category"] == "runtime"
    assert stored["links"] == []
    document = json.loads(result.stdout)["result"]
    assert json.dumps(payload, **CANONICAL) == json.dumps(document, **CANONICAL)


def test_a_refusal_before_the_run_starts_stores_nothing(project: Path) -> None:  # noqa: F811
    result = _run("--json", "--notify", "bogus")
    assert result.exit_code == 1
    assert not (project / DECOY_DIR / "library").exists()


@pytest.mark.parametrize("how", ["flag", "env"])
def test_no_library_stores_no_result(project: Path, how: str) -> None:  # noqa: F811
    args = ("--no-library",) if how == "flag" else ()
    env = {"DECOY_LIBRARY": "off"} if how == "env" else None
    assert _run(*args, env=env).exit_code == EXIT_OK
    assert not (project / DECOY_DIR / "library").exists()


def test_an_unwritable_library_warns_once_for_both_records(project: Path) -> None:  # noqa: F811
    (project / DECOY_DIR).write_text("not a folder", encoding="utf-8")
    result = _run("--json")
    assert result.exit_code == EXIT_OK, result.output
    assert json.loads(result.stdout)["library"]["status"] == "failed"
    assert len([line for line in result.stderr.splitlines() if "warning" in line]) == 1


def test_the_result_file_and_the_record_hold_the_same_document(project: Path) -> None:  # noqa: F811
    assert _run("--result", "r.json").exit_code == EXIT_OK
    (row,) = _rows(project, "run-result")
    written = json.loads((project / "r.json").read_text(encoding="utf-8"))
    assert _stored(project, row.id)["payload"] == written


def test_a_failure_after_the_run_starts_stores_a_result_even_when_it_is_a_usage_failure(
    project: Path,  # noqa: F811
) -> None:
    """V1-1: persistence follows `execution_started`, not the failure category. The engine's
    config-caused `GenerationError` exits 1 (`usage`) but only after the run began."""
    from decoy_engine import GenerationError

    err = GenerationError(code="uniqueness_impossible", message="no")
    with mock.patch("decoy_engine.run_pipeline", side_effect=err):
        result = _run("--json")
    assert result.exit_code == 1, result.output
    (row,) = _rows(project, "run-result")
    payload = _stored(project, row.id)["payload"]
    assert payload["failure"]["category"] == "usage" and payload["exit_code"] == 1


def test_a_usage_refusal_before_the_run_starts_stores_nothing(project: Path) -> None:  # noqa: F811
    (project / "pipelines" / "customers.yaml").write_text("version: 2\ntables: [", encoding="utf-8")
    result = _run("--json")
    assert result.exit_code != EXIT_OK
    assert not (project / DECOY_DIR / "library").exists()


def test_an_unwritable_library_warns_under_quiet_for_the_evidence_record(
    project: Path,  # noqa: F811
) -> None:
    """V1-2: a warning about a lost record is not chatter; --quiet keeps it on stderr."""
    (project / DECOY_DIR).write_text("not a folder", encoding="utf-8")
    result = _run("--quiet")
    assert result.exit_code == EXIT_OK, result.output
    assert len([line for line in result.stderr.splitlines() if "warning" in line]) == 1
    assert "evidence record was not stored" in result.stderr


def test_an_unwritable_library_warns_under_quiet_for_the_result_record(
    project: Path,  # noqa: F811
) -> None:
    """V1-2, result path: a failed run stores no evidence, so the result store is the one to warn."""
    (project / DECOY_DIR).write_text("not a folder", encoding="utf-8")
    with mock.patch("decoy_engine.run_pipeline", side_effect=RuntimeError("boom")):
        result = _run("--quiet")
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert len([line for line in result.stderr.splitlines() if "warning" in line]) == 1
    assert "result record was not stored" in result.stderr


def test_one_resolver_names_the_label_for_a_run_and_for_list(project: Path) -> None:  # noqa: F811
    """DESIGN-2: `library list --pipeline` finds what the run stored, and a layout fault is the
    resolver's `LayoutError` on both sides (a usage error for list, a failed store for the run)."""
    from typer.testing import CliRunner

    from decoy.__main__ import app
    from decoy.cli.io import LayoutError, pipeline_label

    assert _run().exit_code == EXIT_OK
    listed = CliRunner().invoke(app, ["library", "list", "--pipeline", PIPELINE, "--json"])
    assert listed.exit_code == EXIT_OK, listed.output
    assert {row["kind"] for row in json.loads(listed.stdout)["records"]} == {
        "evidence",
        "run-result",
    }

    (project / "decoy.yaml").write_text("kind: not-a-project\n", encoding="utf-8")
    with pytest.raises(LayoutError):
        pipeline_label(project / PIPELINE)


def test_no_library_with_evidence_out_still_writes_only_the_file(project: Path) -> None:  # noqa: F811
    """The `--evidence-out` path reaches the store call, so the off switch must hold there too."""
    assert _run("--no-library", "--evidence-out", "ev.json").exit_code == EXIT_OK
    assert (project / "ev.json").exists()
    assert not (project / DECOY_DIR / "library").exists()
