"""Generate-column options are checked per type at `decoy validate` (GEN-STRICT C1, row 24k).

The QA record's H3 inputs used to pass `validate` and run at exit 0 with the option ignored or
replaced; its H4 inputs passed `validate` and then failed `run` at exit 3 with raw library text.
Both groups now fail `validate` with exit 1 and a code that names the problem, and `run` stops at
its pre-run gate. Where the rejected value can hold a string it is the canary, so a message that
echoes the value fails; numeric rejects (-1, 2, 0) cannot, so those cells assert the message
carries no digit and sits at the exact location.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from typer.testing import CliRunner, Result

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE

runner = CliRunner()
_WIDE = {"COLUMNS": "10000"}
_CANARY = "canary7731"
_TABLE = "people"


def _config(folder: Path, columns: list[dict[str, Any]]) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "tables": [{"name": _TABLE, "row_count": 20, "generate_columns": columns}],
        "targets": {
            _TABLE: {"type": "file", "format": "csv", "path": str(folder / "out" / "people.csv")}
        },
    }
    path = folder / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _validate(folder: Path, columns: list[dict[str, Any]]) -> tuple[Result, list[dict[str, Any]]]:
    result = runner.invoke(app, ["validate", str(_config(folder, columns)), "--json"], env=_WIDE)
    assert "Traceback" not in result.output
    return result, json.loads(result.stdout)["messages"]


def _errors(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if m["severity"] == "error"]


def _value_free(message: str) -> None:
    # Numeric rejects cannot hold a canary: the engine's text for them is fixed, so no digit of
    # the rejected literal (-1, 2, 0) can appear in it.
    assert not re.search(r"\d", message), message


def _no_canary(result: Result) -> None:
    for stream in (result.stdout, _stderr(result)):
        assert _CANARY not in stream.lower(), "an option value reached the output"


def _stderr(result: Result) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


_SEQ = {"name": "id", "type": "sequence", "start": 1}
_CATS = ["alpha", "beta"]


def _cat(**extra: Any) -> dict[str, Any]:
    return {"name": "tier", "type": "categorical", "categories": _CATS, **extra}


def _faker(**extra: Any) -> dict[str, Any]:
    return {"name": "who", "type": "faker", "faker_type": "first_name", **extra}


def _formula(formula: str, **extra: Any) -> dict[str, Any]:
    return {"name": "twice", "type": "formula", "formula": formula, **extra}


# --- AT-C1: each H3 input, refused by the config parse (located by index, engine spelling) ----

_CONFIG_CELLS = [
    pytest.param([_cat(weigths=[_CANARY])], "generate_option_unknown", "[0].weigths", False,
                 id="option-typo"),
    pytest.param([_cat(weights=[-1, 2])], "generate_weights_invalid", "[0].weights[0]", True,
                 id="negative-weight"),
    pytest.param([_faker(null_probability=2)], "generate_option_range",
                 "[0].null_probability", True, id="null-probability-over-1"),
    pytest.param([{**_SEQ, "step": 0}], "generate_option_range", "[0].step", True,
                 id="step-0"),
    pytest.param([_SEQ, {**_SEQ, "start": 5}], "generate_column_duplicate", "[1].name", False,
                 id="duplicate-name"),
    pytest.param([_SEQ, _formula(f"{_CANARY} +")], "generate_formula_invalid",
                 "[1].formula", False, id="formula-syntax"),
]  # fmt: skip


@pytest.mark.parametrize(("columns", "code", "where", "numeric"), _CONFIG_CELLS)
def test_at_c1_config_refusal_names_the_option(
    tmp_path: Path, columns: list[dict[str, Any]], code: str, where: str, numeric: bool
) -> None:
    result, messages = _validate(tmp_path, columns)
    assert result.exit_code == EXIT_USAGE, result.output
    location = f"tables[0].generate_columns{where}"
    hits = [m for m in _errors(messages) if (m["code"], m.get("location")) == (code, location)]
    assert hits, {(m["code"], m.get("location")) for m in _errors(messages)}
    if numeric:
        _value_free(hits[0]["message"])
    _no_canary(result)


# --- AT-C1: each H3 input that needs the Faker registry or the sibling columns ----------------

_PLAN_CELLS = [
    pytest.param([_faker(faker_type=f"{_CANARY}_provider")], "generate_faker_type_unknown",
                 "who", "faker_type", id="faker-type"),
    pytest.param([_faker(locale=f"{_CANARY}_YY")], "generate_locale_unknown", "who",
                 "locale", id="locale"),
    pytest.param([_faker(faker_kwargs={f"{_CANARY}_k": f"{_CANARY}_v"})], "generate_faker_kwargs_unknown",
                 "who", "faker_kwargs", id="faker-kwargs"),
    pytest.param([{**_SEQ, "name": "a"}, _formula(f"ghost + 1  # {_CANARY}", references=["ghost"])],
                 "generate_formula_reference_unknown", "twice", "references.0",
                 id="formula-reference-unknown"),
    pytest.param([{**_SEQ, "name": "a"}, _formula(f"a * 2  # {_CANARY}")],
                 "generate_formula_reference_missing", "twice", "formula",
                 id="formula-no-references"),
    pytest.param([{**_SEQ, "name": "a"}, _formula(f"{{a}} * 2  # {_CANARY}", references=["a"])],
                 "generate_formula_template_syntax", "twice", "formula",
                 id="formula-template-form"),
]  # fmt: skip


@pytest.mark.parametrize(("columns", "code", "column", "key"), _PLAN_CELLS)
def test_at_c1_plan_refusal_names_table_column_and_option(
    tmp_path: Path, columns: list[dict[str, Any]], code: str, column: str, key: str
) -> None:
    result, messages = _validate(tmp_path, columns)
    assert result.exit_code == EXIT_USAGE, result.output
    hits = [m for m in _errors(messages) if m["code"] == code]
    assert hits, [m["code"] for m in _errors(messages)]
    text = hits[0]["message"]
    assert f"table '{_TABLE}', column '{column}'" in text, text
    assert f"option '{key}'" in text, text
    _no_canary(result)


def test_at_c1_human_output_names_the_location(tmp_path: Path) -> None:
    # The human line carries the engine's fixed text and the location; the code is in --json.
    result = runner.invoke(
        app, ["validate", str(_config(tmp_path, [_cat(weigths=[_CANARY])]))], env=_WIDE
    )
    assert result.exit_code == EXIT_USAGE
    text = " ".join(result.output.split())
    assert "Generate column option is not known for this column type." in text
    assert "tables[0].generate_columns[0].weigths" in text
    _no_canary(result)


def test_at_c1_boundary_values_still_validate(tmp_path: Path) -> None:
    columns = [
        {**_SEQ, "step": -1},
        _cat(weights=[0, 1], null_probability=1),
        _faker(locale=["en_US", "fr_FR"], null_probability=0),
        _formula("id * 2", references=["id"]),
    ]
    result, messages = _validate(tmp_path, columns)
    assert result.exit_code == EXIT_OK, _errors(messages)


# --- AT-C2: each H4 input fails validate, and run stops at its gate (never exit 3) ----------

# Each cell: columns, code, then what the message must name. `where` is the config location for
# a parse-time refusal; `column` and `option` are the plan-time table/column/option text.
_H4_CELLS = [
    pytest.param([_cat(weights=[0, 0])], "generate_weights_invalid",
                 {"where": "tables[0].generate_columns[0].weights", "numeric": True},
                 id="zero-sum-weights"),
    pytest.param([{"name": "tier", "type": "categorical", "categories": [_CANARY, 1]}],
                 "generate_categories_mixed", {"column": "tier", "option": "categories"},
                 id="mixed-categories"),
    pytest.param([{**_SEQ, "name": "order_id"},
                  {"name": "n", "type": "grouped_series", "group_by": "order_id",
                   "order_by": "order_id"}],
                 "grouped_series_group_by_equals_order_by",
                 {"column": "n", "option": "order_by"}, id="group-by-equals-order-by"),
    pytest.param([{**_SEQ, "name": "a"},
                  {"name": "d", "type": "derived", "expression": f'b + (1 if "{_CANARY}" else 0)'},
                  {**_SEQ, "name": "b"}],
                 "generate_column_forward_reference",
                 {"column": "d", "option": "expression"}, id="derived-forward-reference"),
]  # fmt: skip


def _names(message: str, location: str | None, names: dict[str, Any]) -> None:
    if "where" in names:
        assert location == names["where"], location
        if names.get("numeric"):
            _value_free(message)
    else:
        assert f"table '{_TABLE}', column '{names['column']}'" in message, message
        assert f"option '{names['option']}'" in message, message


@pytest.mark.parametrize(("columns", "code", "names"), _H4_CELLS)
def test_at_c2_validate_refuses_with_the_code(
    tmp_path: Path, columns: list[dict[str, Any]], code: str, names: dict[str, Any]
) -> None:
    result, messages = _validate(tmp_path, columns)
    assert result.exit_code == EXIT_USAGE, result.output
    hits = [m for m in _errors(messages) if m["code"] == code]
    assert hits, [m["code"] for m in _errors(messages)]
    _names(hits[0]["message"], hits[0].get("location"), names)
    _no_canary(result)


@pytest.mark.parametrize(("columns", "code", "names"), _H4_CELLS)
def test_at_c2_run_stops_at_the_gate(
    tmp_path: Path, columns: list[dict[str, Any]], code: str, names: dict[str, Any]
) -> None:
    config = _config(tmp_path, columns)
    result = runner.invoke(app, ["run", str(config), "--json"], env=_WIDE)
    assert "Traceback" not in result.output
    assert result.exit_code == EXIT_USAGE, result.output
    assert code in result.stdout
    assert not (tmp_path / "out" / "people.csv").exists()
    if "where" in names:
        assert names["where"] in result.stdout, result.stdout
        if names.get("numeric"):
            sent = [m for m in json.loads(result.stdout)["messages"] if m["code"] == code]
            assert sent, result.stdout
            _value_free(sent[0]["message"])
    else:
        assert f"table '{_TABLE}', column '{names['column']}'" in result.stdout, result.stdout
        assert f"option '{names['option']}'" in result.stdout, result.stdout
    _no_canary(result)


# --- AT-C4: `decoy schema` closes each generate type ------------------------------------------

# The plan's 11 types plus `constant`, `distribution` and `lookup`, added to the engine after it was written.
_GENERATE_TYPES = (
    "faker", "sequence", "categorical", "formula", "reference", "statistical", "derived",
    "derived_aggregate", "grouped_series", "windowed_date", "group_key", "constant",
    "distribution", "lookup",
)  # fmt: skip


def _generate_column_schema(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs") or schema.get("definitions") or {}
    return defs["GenerateColumnConfig"]


def test_at_c4_schema_closes_every_generate_type() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == EXIT_OK, result.output
    column = _generate_column_schema(json.loads(result.stdout))
    closed: dict[str, dict[str, Any]] = {}
    for branch in column.get("allOf", []):
        const = branch.get("if", {}).get("properties", {}).get("type", {}).get("const")
        if const is not None:
            closed[const] = branch["then"]
    assert set(closed) == set(_GENERATE_TYPES)
    for type_name, then in closed.items():
        assert then.get("additionalProperties") is False, type_name
        assert {"name", "type", "pooled", "null_probability"} <= set(then["properties"]), type_name


def test_at_c4_schema_refuses_the_typo_and_accepts_a_good_column() -> None:
    result = runner.invoke(app, ["schema"])
    schema = json.loads(result.stdout)
    column = {
        **_generate_column_schema(schema),
        "$defs": schema.get("$defs", {}),
    }
    validator = jsonschema.Draft202012Validator(column)
    assert validator.is_valid(_cat(weights=[1, 2]))
    assert not validator.is_valid(_cat(weigths=[1, 2]))
