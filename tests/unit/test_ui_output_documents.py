"""`emit_json_document` and the two stdout documents that go through it.

`decoy schema` (default mode) and `decoy scan --output -` print one JSON document that is not
the `--json` envelope. The bytes are a contract: users pipe them.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.ui.output import OutputMode, OutputState, emit_json_document


def _state(mode: OutputMode) -> OutputState:
    from decoy.ui.output import _make_console

    return OutputState(
        mode=mode,
        verbose=False,
        console=_make_console(stderr=False),
        err_console=_make_console(stderr=True),
    )


# AT-CL2-5 ---------------------------------------------------------------------------------


def test_default_mode_writes_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    emit_json_document(_state(OutputMode.default), {"b": 1, "a": ["é"]}, indent=None)
    assert out.getvalue() == '{"b": 1, "a": ["\\u00e9"]}\n'


def test_indent_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    emit_json_document(_state(OutputMode.default), {"a": 1}, indent=2)
    assert out.getvalue() == '{\n  "a": 1\n}\n'


@pytest.mark.parametrize("mode", [OutputMode.json, OutputMode.quiet])
def test_other_modes_are_a_programming_error(
    monkeypatch: pytest.MonkeyPatch, mode: OutputMode
) -> None:
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    with pytest.raises(ValueError, match="default"):
        emit_json_document(_state(mode), {"a": "CANARY-1"}, indent=None)
    assert out.getvalue() == ""


def test_the_error_names_no_document_content(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError) as caught:
        emit_json_document(_state(OutputMode.json), {"a": "CANARY-1"}, indent=None)
    assert "CANARY-1" not in str(caught.value)


# AT-CL2-4: control, the bytes do not change ----------------------------------------------


def test_schema_stdout_bytes_are_indented_ascii_json() -> None:
    from decoy_engine import PipelineConfig

    result = CliRunner().invoke(app, ["--no-update-check", "schema"])
    assert result.exit_code == 0, result.output
    expected = json.dumps(PipelineConfig.model_json_schema(), indent=2) + "\n"
    assert result.stdout
    assert result.stdout.encode() == expected.encode()


def test_streamed_scan_stdout_bytes_are_one_compact_ascii_line(tmp_path: Path) -> None:
    src = tmp_path / "données.csv"
    src.write_text("id,name\n1,a\n2,b\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["--no-update-check", "scan", str(src), "--has-header", "--output", "-"]
    )
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert out
    assert out.endswith("}\n") and out.count("\n") == 1
    # Round trip pins both separators and ensure_ascii: a changed spelling would differ.
    assert out == json.dumps(json.loads(out)) + "\n"
    assert "\\u00e9" in out
    assert out.isascii()
