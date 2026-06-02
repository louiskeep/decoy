"""End-to-end tests for `decoy explain`."""

from __future__ import annotations

import json as _json

from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.explain import topic_names


runner = CliRunner()


def test_explain_help_includes_examples():
    result = runner.invoke(app, ["explain", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_explain_no_topic_lists_index():
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0
    # Listing should mention several known topics.
    for topic in ("modes", "transforms", "disguises", "output"):
        assert topic in result.stdout


def test_explain_known_topic_renders_panel():
    result = runner.invoke(app, ["explain", "modes"])
    assert result.exit_code == 0
    # Panel title carries the topic name.
    assert "modes" in result.stdout
    assert "mask" in result.stdout
    assert "generate" in result.stdout


def test_explain_unknown_topic_suggests_close_match():
    result = runner.invoke(app, ["explain", "stom"])
    assert result.exit_code == 1
    # Cause + did-you-mean hint per CLI_UX_GUIDE.md section 9.
    assert "unknown topic" in result.stderr.lower()
    assert "storm" in result.stderr


def test_explain_unknown_topic_no_close_match_falls_back_to_list_hint():
    result = runner.invoke(app, ["explain", "zzzzzz"])
    assert result.exit_code == 1
    # No close match -- hint should point to the listing command.
    assert "decoy explain" in result.stderr


def test_explain_json_emits_full_topic():
    result = runner.invoke(app, ["explain", "transforms", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "explain"
    assert payload["status"] == "ok"
    assert payload["topic"] == "transforms"
    assert payload["body"]
    assert payload["summary"]


def test_explain_json_index_lists_topics():
    result = runner.invoke(app, ["explain", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert {t["name"] for t in payload["topics"]} == set(topic_names())


def test_explain_json_unknown_topic_emits_error_envelope():
    result = runner.invoke(app, ["explain", "stom", "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["did_you_mean"] == "storm"


def test_explain_quiet_produces_empty_stdout():
    result = runner.invoke(app, ["explain", "modes", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_topic_names_covers_load_bearing_concepts():
    """Sanity check: the topic set must include the load-bearing concepts.

    CLI.4 (2026-06-02): forecast topic dropped (FORECAST retired under
    storm-reframe-C). The remaining topics cover the V2 surface.
    """
    names = set(topic_names())
    expected = {"modes", "transforms", "disguises", "output", "pipeline", "storm", "keys"}
    missing = expected - names
    assert not missing, f"missing topics: {missing}"
    # CLI.1 + CLI.4 (2026-06-02): forecast topic removed; the explain
    # body across other topics now describes the removal rather than
    # documenting a deleted command.
    assert "forecast" not in names
