"""`emit_error`: the one place a command prints a failure, in every output mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decoy.ui.output import emit_error, setup_output

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "schemas" / "decoy-error-v1.schema.json")
    .read_text(encoding="utf-8")
)


def _state(mode: str):
    return setup_output(mode == "json", mode == "quiet", False)


@pytest.mark.parametrize("mode", ["default", "quiet"])
def test_human_error_goes_to_stderr_in_every_non_json_mode(capsys, mode: str) -> None:
    emit_error(_state(mode), "fit", "could not read the source.", hint="check the path.")

    out, err = capsys.readouterr()
    assert out == ""
    assert err.splitlines() == ["error: could not read the source.", "  hint: check the path."]


def test_human_error_keeps_brackets_literal(capsys) -> None:
    emit_error(_state("default"), "fit", "install 'decoy-engine[vault]' first")

    assert "decoy-engine[vault]" in capsys.readouterr().err


def test_human_error_shows_the_code_before_the_message(capsys) -> None:
    emit_error(_state("default"), "subset", "bad config.", code="subset_cli_usage")

    assert capsys.readouterr().err.splitlines() == ["error: [subset_cli_usage] bad config."]


def test_json_error_is_one_stdout_object_and_nothing_on_stderr(capsys) -> None:
    emit_error(
        _state("json"),
        "fit",
        "bad input",
        code="dp_epsilon_invalid",
        hint="use a positive epsilon.",
        context={"source": "a.csv"},
    )

    out, err = capsys.readouterr()
    assert err == ""
    assert len(out.splitlines()) == 1
    assert json.loads(out) == {
        "command": "fit",
        "status": "error",
        "error": "bad input",
        "code": "dp_epsilon_invalid",
        "hint": "use a positive epsilon.",
        "source": "a.csv",
    }


def test_json_error_omits_absent_members(capsys) -> None:
    emit_error(_state("json"), "list", "unknown kind")

    assert json.loads(capsys.readouterr().out) == {
        "command": "list",
        "status": "error",
        "error": "unknown kind",
    }


def test_json_error_validates_against_the_schema(capsys) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    emit_error(_state("json"), "run", "boom", code="a.b_c", context={"outputs": [{"n": 1}]})

    jsonschema.validate(json.loads(capsys.readouterr().out), SCHEMA)


@pytest.mark.parametrize("key", ["command", "status", "error", "code", "hint"])
def test_context_may_not_shadow_a_fixed_member(capsys, key: str) -> None:
    with pytest.raises(ValueError):
        emit_error(_state("json"), "fit", "x", context={key: "y"})

    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("bad", ["Bad Code", "ok\n", "", "1abc", "a-b", "A"])
def test_code_must_match_the_schema_pattern(capsys, bad: str) -> None:
    with pytest.raises(ValueError):
        emit_error(_state("json"), "fit", "x", code=bad)

    assert capsys.readouterr() == ("", "")


def test_a_bad_code_is_refused_in_human_mode_too(capsys) -> None:
    with pytest.raises(ValueError):
        emit_error(_state("default"), "fit", "x", code="Bad Code")

    assert capsys.readouterr() == ("", "")


def test_schema_code_pattern_is_the_emitter_rule() -> None:
    assert SCHEMA["properties"]["code"]["pattern"] == "^[a-z][a-z0-9_.]*$"
