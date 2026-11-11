"""`validate compile` sees the relationships the config declares.

The no-profile compile built its sentinel profile with no relationships, so a pipeline that
declares one printed "no FK dependencies detected" and missed the `namespace_missing` error that
`validate` reports.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner, Result

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qa_first_user"
_NO_FK_TEXT = "no FK dependencies detected"


def _stage(tmp_path: Path, name: str) -> Path:
    for fixture in ("patients.csv", "visits.csv", name):
        shutil.copy(_FIXTURES / fixture, tmp_path / fixture)
    return tmp_path / name


def _unequal_composite(tmp_path: Path) -> Path:
    """A relationship whose child names two columns against one parent column."""
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    text = config.read_text(encoding="utf-8").replace(
        "- {table: visits, columns: [patient_id]}",
        "- {table: visits, columns: [patient_id, diagnosis]}",
    )
    config.write_text(text, encoding="utf-8")
    return config


def _flat(result: Result) -> str:
    """Output with Rich's line wrapping undone, so a phrase split across lines still matches."""
    return " ".join(result.output.split())


def _clean(result: Result) -> None:
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output
    assert "internal error" not in result.output


def test_compile_reports_the_namespace_error(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", "compile", str(config), "--json"])
    _clean(result)
    assert result.exit_code == EXIT_USAGE
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["code"] == "namespace_missing"


def test_compile_human_output_names_the_error_not_no_dependencies(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", "compile", str(config), "--explain"])
    _clean(result)
    assert result.exit_code == EXIT_USAGE
    assert "namespace_missing" in result.output
    assert _NO_FK_TEXT not in _flat(result)


def test_compile_orders_the_parent_before_the_child(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    result = runner.invoke(app, ["validate", "compile", str(config), "--explain", "--json"])
    _clean(result)
    assert result.exit_code == EXIT_OK, result.output
    order = [node["table"] for node in json.loads(result.stdout)["ordering"]]
    assert "patients" in order and "visits" in order
    assert order.index("patients") < order.index("visits")


def test_compile_explain_no_longer_says_no_dependencies(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    result = runner.invoke(app, ["validate", "compile", str(config), "--explain"])
    _clean(result)
    assert result.exit_code == EXIT_OK, result.output
    assert _NO_FK_TEXT not in _flat(result)


def test_unequal_composite_is_a_compile_error(tmp_path: Path) -> None:
    config = _unequal_composite(tmp_path)
    result = runner.invoke(app, ["validate", "compile", str(config), "--json"])
    _clean(result)
    assert result.exit_code == EXIT_USAGE
    assert json.loads(result.stdout)["status"] == "error"


def test_unequal_composite_is_a_compile_error_in_the_gate(tmp_path: Path) -> None:
    config = _unequal_composite(tmp_path)
    result = runner.invoke(app, ["validate", str(config), "--json"])
    _clean(result)
    assert result.exit_code == EXIT_USAGE
    messages = json.loads(result.stdout)["messages"]
    assert ("compile", "error", "compile_error") in {
        (m["layer"], m["severity"], m["code"]) for m in messages
    }
