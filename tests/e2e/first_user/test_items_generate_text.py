"""Generation text the user reads: `validate compile --explain` and the explain topics (GEN-CLI C3).

AT-20 to AT-22 and the dead-pointer check. The topic tests read the engine's registries at test
time, so a type or strategy the engine adds without a CLI edit turns them red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from decoy_engine.config import generate_option_catalog
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.explain import topic_names

runner = CliRunner()
SRC = Path(__file__).resolve().parents[3] / "src" / "decoy"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _seq(name: str, rows: int) -> dict:
    return {
        "name": name,
        "row_count": rows,
        "generate_columns": [{"name": "id", "type": "sequence", "start": 1, "step": 1}],
    }


def _qa_config(folder: Path) -> Path:
    """Three parents declared after their child, so declaration order differs from build order."""
    orders = {
        "name": "orders",
        "row_count": 100,
        "generate_columns": [
            {
                "name": f"{p}_id",
                "type": "reference",
                "reference_table": p,
                "reference_column": "id",
            }
            for p in ("customers", "products", "stores")
        ],
    }
    tables = [orders, _seq("customers", 30), _seq("products", 20), _seq("stores", 10)]
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {},
        "tables": tables,
        "targets": {
            t["name"]: {"type": "file", "format": "csv", "path": f"{t['name']}.csv"} for t in tables
        },
    }
    path = folder / "qa.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _topic_body(name: str) -> str:
    res = runner.invoke(app, ["explain", name, "--json"])
    assert res.exit_code == 0, res.output
    return json.loads(res.stdout)["body"]


# --- AT-20 -------------------------------------------------------------------


def test_compile_explain_lists_generation_order_and_references(tmp_path: Path) -> None:
    cfg = _qa_config(tmp_path)

    res = runner.invoke(app, ["validate", "compile", str(cfg), "--explain"], terminal_width=200)

    assert res.exit_code == 0, res.output
    text = _flat(res.output)
    assert "no FK dependencies detected" not in text
    order = text[text.index("Generation order") :]
    positions = [order.index(t) for t in ("customers", "products", "stores", "orders")]
    assert positions == sorted(positions), order
    for parent in ("customers", "products", "stores"):
        assert f"{parent}_id" in text and f"{parent}.id" in text


def test_compile_explain_json_has_generation(tmp_path: Path) -> None:
    cfg = _qa_config(tmp_path)

    res = runner.invoke(app, ["validate", "compile", str(cfg), "--explain", "--json"])

    assert res.exit_code == 0, res.output
    generation = json.loads(res.stdout)["generation"]
    assert [row["table"] for row in generation["order"]] == [
        "customers",
        "products",
        "stores",
        "orders",
    ]
    assert generation["order"][-1]["parents"] == ["customers", "products", "stores"]
    assert len(generation["references"]) == 3
    by_name = {t["name"]: t for t in generation["tables"]}
    assert by_name["orders"]["rows"] == 100
    assert by_name["customers"]["columns"] == [{"name": "id", "type": "sequence"}]


# --- AT-21 -------------------------------------------------------------------


def _type_blocks(body: str) -> dict[str, str]:
    """The topic's per-type blocks: a line holding only the type name, then indented lines."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in body.splitlines():
        match = re.fullmatch(r"  (\w+)", line)
        if match:
            current = blocks.setdefault(match.group(1), [])
        elif current is not None and line.startswith("      "):
            current.append(line)
        else:
            current = None
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def test_generation_topic_names_every_catalog_type_and_option() -> None:
    catalog = generate_option_catalog()
    assert catalog, "the engine returned an empty catalog"
    body = _topic_body("generation")
    blocks = _type_blocks(body)

    for type_, spec in catalog.items():
        assert type_ in blocks, f"type {type_} missing from `explain generation`"
        options = {*spec.required, *spec.optional}
        for selector, by_value in spec.required_when.items():
            options.add(selector)
            for keys in by_value.values():
                options.update(keys)
        for option in options:
            assert re.search(rf"\b{re.escape(option)}\b", blocks[type_]), (type_, option)
    for option in next(iter(catalog.values())).common:
        assert option in body


def test_generation_topic_states_the_workflow_and_the_rules() -> None:
    flat = _flat(_topic_body("generation"))

    for needle in (
        "decoy fit",
        "decoy run",
        "decoy report fidelity",
        "--generate",
        "folder that holds the YAML",
        "--master-key",
        "fidelity_warn_threshold",
        "--rows",
        "decoy explain unique",
    ):
        assert needle in flat, needle


def test_every_explain_pointer_in_user_text_names_a_real_topic() -> None:
    topics = set(topic_names())
    seen: set[str] = set()
    for path in SRC.rglob("*.py"):
        seen.update(re.findall(r"decoy explain ([a-z][a-z-]*)", path.read_text(encoding="utf-8")))
    assert seen - topics - {"topic"} == set()


# --- AT-22 -------------------------------------------------------------------


def test_transforms_topic_lists_exactly_the_registered_strategies() -> None:
    listed = runner.invoke(app, ["list", "strategies", "--json"])
    assert listed.exit_code == 0, listed.output
    registered = {entry["name"] for entry in json.loads(listed.stdout)["strategies"]}
    lines = _topic_body("transforms").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Mask strategies"))
    names: set[str] = set()
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        names.add(line.split()[0])

    assert names == registered


def test_transforms_topic_uses_the_yaml_key_and_drops_stale_text() -> None:
    body = _topic_body("transforms")

    assert "strategy:" in body
    assert "masking_rule" not in body
    assert "future --mask" not in body
    assert "decoy explain generation" in body


@pytest.mark.parametrize("topic", ["pipeline", "yaml"])
def test_pipeline_and_yaml_topics_state_the_path_rule(topic: str) -> None:
    flat = _flat(_topic_body(topic))

    assert "folder that holds the YAML" in flat
    assert "decoy explain generation" in flat
    assert "reference_table" in flat
