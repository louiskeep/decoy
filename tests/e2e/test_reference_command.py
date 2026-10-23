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


@pytest.mark.parametrize(
    "old", ["strategies", "providers", "checksums", "validators", "templates"]
)
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
