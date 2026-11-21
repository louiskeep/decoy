"""E2E tests for the S3b reference vocabulary: `decoy list KIND` / `show KIND`.

Covers the unified dispatch that folded the `strategies`/`providers`/
`checksums`/`validators` sub-apps, the `templates` sub-app, and `schema` into
two verbs:

  - `list KIND` for all six kinds (reads the LIVE engine registry);
  - `show KIND NAME` detail for strategy/provider/template, plus `show schema`;
  - per-kind validation (NAME-required, list-only no-detail, unknown kind);
  - the old top-level sub-apps are gone ("No such command").

The template-body specifics live in `test_templates_command.py`; the
registry-correspondence invariants live in `test_cockpit.py`.
"""

from __future__ import annotations

import json as _json

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


# ---------------------------------------------------------------------------
# list KIND -- all six kinds exit 0 and show the live registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, payload_key, known_member",
    [
        ("strategies", "strategies", "fpe"),
        ("providers", "providers", "person_name"),
        ("checksums", "schemes", "luhn"),
        ("validators", "validators", "fk_intact"),
        ("templates", "templates", "hipaa"),
        ("disguises", "disguises", "hipaa"),
    ],
)
def test_list_kind_exits_0_and_shows_known_member(kind, payload_key, known_member):
    # Human mode exits 0 and names the known member.
    result = runner.invoke(app, ["list", kind])
    assert result.exit_code == 0, result.output
    assert known_member in result.stdout

    # JSON envelope carries the new-surface command string + the member.
    jresult = runner.invoke(app, ["list", kind, "--json"])
    assert jresult.exit_code == 0, jresult.output
    payload = _json.loads(jresult.stdout)
    assert payload["command"] == f"list {kind}"
    assert payload["status"] == "ok"
    entries = payload[payload_key]
    # Entries are either bare strings or objects carrying a name and/or id.
    flat: set[str] = set()
    for e in entries:
        if isinstance(e, str):
            flat.add(e)
        else:
            flat.update(v for v in (e.get("name"), e.get("id")) if v)
    assert known_member in flat


def test_list_disguises_lists_bundles_with_rule_counts():
    """H8: `list disguises` reads the engine's Disguise bundles live."""
    result = runner.invoke(app, ["list", "disguises", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "list disguises"
    by_id = {d["id"]: d for d in payload["disguises"]}
    assert "hipaa" in by_id, "the hipaa disguise bundle must be listed"
    # Rule counts come straight off the bundle (hipaa Safe Harbor is the
    # richest bundle); every entry reports a positive integer count.
    assert by_id["hipaa"]["rules"] > 0
    assert all(isinstance(d["rules"], int) for d in payload["disguises"])

    # Anti-drift: the CLI set equals the engine's load_disguises() set.
    from decoy_engine.disguises import load_disguises

    engine_ids = {d.id for d in load_disguises()}
    assert set(by_id) == engine_ids


def test_list_disguises_human_shows_hipaa():
    result = runner.invoke(app, ["list", "disguises"])
    assert result.exit_code == 0
    assert "hipaa" in result.stdout


# ---------------------------------------------------------------------------
# show KIND NAME -- detail views
# ---------------------------------------------------------------------------


def test_show_strategy_detail():
    result = runner.invoke(app, ["show", "strategy", "fpe", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "show strategy"
    assert payload["status"] == "ok"
    assert payload["name"] == "fpe"


def test_show_provider_detail():
    result = runner.invoke(app, ["show", "provider", "person_name", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "show provider"
    assert payload["name"] == "person_name"


def test_show_template_detail():
    result = runner.invoke(app, ["show", "template", "hipaa"])
    assert result.exit_code == 0, result.output
    assert result.stdout.strip(), "template body should print to stdout"


def test_show_schema_prints_json_schema():
    result = runner.invoke(app, ["show", "schema"])
    assert result.exit_code == 0, result.output
    parsed = _json.loads(result.stdout)
    assert "$defs" in parsed or "properties" in parsed


def test_show_schema_output_writes_file(tmp_path):
    out = tmp_path / "decoy.schema.json"
    result = runner.invoke(app, ["show", "schema", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    parsed = _json.loads(out.read_text(encoding="utf-8"))
    assert "$defs" in parsed or "properties" in parsed


def test_show_schema_rejects_stray_name():
    """`show schema` takes no NAME; a stray positional is a clean usage error."""
    result = runner.invoke(app, ["show", "schema", "hipaa"])
    assert result.exit_code == 1
    assert "no NAME" in result.output or "takes no" in result.output


# ---------------------------------------------------------------------------
# per-kind validation
# ---------------------------------------------------------------------------


def test_show_strategy_without_name_is_usage_error():
    result = runner.invoke(app, ["show", "strategy"])
    assert result.exit_code == EXIT_USAGE
    assert "requires a NAME" in result.stderr


@pytest.mark.parametrize("kind", ["provider", "template"])
def test_show_detail_kind_without_name_is_usage_error(kind):
    result = runner.invoke(app, ["show", kind])
    assert result.exit_code == EXIT_USAGE
    assert "requires a NAME" in result.stderr


@pytest.mark.parametrize("kind", ["checksum", "validator"])
def test_show_list_only_kind_gives_helpful_no_detail_message(kind):
    result = runner.invoke(app, ["show", kind, "luhn"])
    assert result.exit_code == EXIT_USAGE
    assert "no detail view" in result.stderr
    assert "strategy/provider/template/schema" in result.stderr


def test_show_checksum_json_no_detail():
    result = runner.invoke(app, ["show", "checksum", "luhn", "--json"])
    assert result.exit_code == EXIT_USAGE
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["kind"] == "checksum"


def test_list_unknown_kind_names_valid_kinds():
    result = runner.invoke(app, ["list", "bogus"])
    assert result.exit_code == EXIT_USAGE
    err = result.stderr
    assert "unknown kind" in err
    for kind in ("strategies", "providers", "checksums", "validators", "templates", "disguises"):
        assert kind in err


def test_show_unknown_kind_names_valid_kinds():
    result = runner.invoke(app, ["show", "bogus"])
    assert result.exit_code == EXIT_USAGE
    assert "unknown kind" in result.stderr


def test_show_plural_cross_suggests_singular_with_name():
    """`show strategies` should hint the singular `show strategy NAME`."""
    result = runner.invoke(app, ["show", "strategies"])
    assert result.exit_code == EXIT_USAGE
    assert "decoy show strategy NAME" in result.stderr


def test_list_singular_cross_suggests_plural():
    """`list strategy` should hint the plural `list strategies`."""
    result = runner.invoke(app, ["list", "strategy"])
    assert result.exit_code == EXIT_USAGE
    assert "decoy list strategies" in result.stderr


# ---------------------------------------------------------------------------
# the old top-level sub-apps are gone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("old", ["strategies", "providers", "checksums", "validators", "templates"])
def test_old_subapps_removed(old):
    result = runner.invoke(app, [old, "list"])
    assert result.exit_code != 0
    assert "No such command" in result.output


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


def test_list_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_show_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["show", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


# ---------------------------------------------------------------------------
# list generate-types / list faker-types -- GEN-14, read the live engine catalogs
# ---------------------------------------------------------------------------


def test_list_generate_types_names_exactly_the_catalog_keys():
    from decoy_engine.config import generate_option_catalog

    catalog = generate_option_catalog()
    result = runner.invoke(app, ["list", "generate-types", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "list generate-types"
    assert payload["status"] == "ok"
    assert payload["count"] == len(catalog)
    assert [t["type"] for t in payload["generate_types"]] == list(catalog)
    for entry in payload["generate_types"]:
        spec = catalog[entry["type"]]
        assert entry["required"] == list(spec.required)
        assert entry["optional"] == list(spec.optional)
    assert payload["common_options"] == list(next(iter(catalog.values())).common)


def test_list_generate_types_human_output_names_each_type():
    from decoy_engine.config import generate_option_catalog

    result = runner.invoke(app, ["list", "generate-types"])
    assert result.exit_code == 0, result.output
    for type_ in generate_option_catalog():
        assert type_ in result.stdout


def test_list_faker_types_equals_the_engine_provider_list():
    from decoy_engine import list_generate_faker_providers

    result = runner.invoke(app, ["list", "faker-types", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "list faker-types"
    assert payload["status"] == "ok"
    assert payload["faker_types"] == list(list_generate_faker_providers())
    assert payload["count"] == len(payload["faker_types"])


def test_list_faker_types_human_output_names_a_provider():
    from decoy_engine import list_generate_faker_providers

    first = next(iter(list_generate_faker_providers()))
    result = runner.invoke(app, ["list", "faker-types"])
    assert result.exit_code == 0, result.output
    assert first in result.stdout


def test_list_unknown_kind_lists_the_new_kinds_too():
    result = runner.invoke(app, ["list", "bogus"])
    assert result.exit_code == EXIT_USAGE
    assert "generate-types" in result.stderr
    assert "faker-types" in result.stderr


def test_list_singular_generate_type_cross_suggests_plural():
    result = runner.invoke(app, ["list", "generate-type"])
    assert result.exit_code == EXIT_USAGE
    assert "decoy list generate-types" in result.stderr


# ---------------------------------------------------------------------------
# list codesets, derived kind help, one_of, provider wording -- GEN-CATALOG GC3
# ---------------------------------------------------------------------------


def test_list_codesets_json_equals_the_engine_catalog():
    from decoy_engine import code_set_catalog

    catalog = code_set_catalog()
    result = runner.invoke(app, ["list", "codesets", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "list codesets"
    assert payload["status"] == "ok"
    assert payload["count"] == len(catalog)
    assert [c["name"] for c in payload["codesets"]] == list(catalog)
    for entry in payload["codesets"]:
        assert entry["description"] == catalog[entry["name"]]


def test_list_codesets_human_output_names_icd10_and_the_lookup_tip():
    result = runner.invoke(app, ["list", "codesets"])
    assert result.exit_code == 0, result.output
    assert "icd10" in result.stdout
    assert "codeset:" in result.stdout


def test_list_singular_codeset_cross_suggests_plural():
    result = runner.invoke(app, ["list", "codeset"])
    assert result.exit_code == EXIT_USAGE
    assert "decoy list codesets" in result.stderr


def _list_command():
    import typer.main

    group = typer.main.get_command(app)
    return group.commands["list"]  # type: ignore[attr-defined]


def _kinds_after(text: str, marker: str) -> set[str]:
    import re

    tail = " ".join(text.split()).split(marker, 1)[1]
    return {k for k in re.split(r"[|,.\s]+", tail) if k}


def test_every_list_kind_inventory_equals_the_reader_table():
    from decoy.cli.reference import _LIST_READERS

    kinds = set(_LIST_READERS)
    cmd = _list_command()
    arg = next(p for p in cmd.params if p.name == "kind")
    assert _kinds_after(arg.help, "What to list:") == kinds
    epilog = " ".join((cmd.epilog or "").split())
    kinds_line = epilog.split("Kinds:", 1)[1].split("See also", 1)[0]
    assert _kinds_after("x " + kinds_line, "x") == kinds
    doc = " ".join((cmd.help or "").split())
    for kind in kinds:
        assert kind in doc, f"{kind} missing from the list command help"
    result = runner.invoke(app, ["list", "nope"])
    for kind in kinds:
        assert kind in result.stderr


def test_list_generate_types_carries_one_of_from_the_engine():
    from decoy_engine.config import generate_option_catalog

    catalog = generate_option_catalog()
    result = runner.invoke(app, ["list", "generate-types", "--json"])
    payload = _json.loads(result.stdout)
    for entry in payload["generate_types"]:
        assert entry["one_of"] == list(catalog[entry["type"]].one_of)
    lookup = next(e for e in payload["generate_types"] if e["type"] == "lookup")
    assert lookup["one_of"] == ["file", "codeset"]
    human = runner.invoke(app, ["list", "generate-types"])
    assert "one of: file, codeset" in " ".join(human.stdout.split())
    explain = runner.invoke(app, ["explain", "generation"])
    assert "exactly one of: file, codeset" in explain.stdout


def test_explain_generation_points_at_the_value_lists():
    result = runner.invoke(app, ["explain", "generation"])
    assert "decoy list faker-types" in result.stdout
    assert "decoy list codesets" in result.stdout


def test_providers_wording_does_not_say_generation_provider():
    helped = runner.invoke(app, ["list", "--help"])
    assert "generation provider" not in " ".join(helped.stdout.split())
    listed = runner.invoke(app, ["list", "providers"])
    assert "generation provider" not in " ".join(listed.stdout.split())
    # The registry serves mask `provider:` columns and generate `type: provider` columns.
    for text in (" ".join(helped.stdout.split()), " ".join(listed.stdout.split())):
        assert "provider:" in text and "type: provider" in text
    tip = " ".join(listed.stdout.split())
    assert "faker-types" in tip and "type: faker" in tip
