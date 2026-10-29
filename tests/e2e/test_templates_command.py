"""End-to-end tests for `decoy list templates` / `decoy show template NAME`.

S3b (CLI redesign) folded the former `templates list`/`templates show`
sub-app into the unified `list`/`show` vocabulary. These tests cover the
template-specific behaviour (raw-YAML dump, pipe-to-validate, did-you-mean);
the generic dispatch and unknown-kind handling live in
`test_reference_command.py`.
"""

from __future__ import annotations

import json as _json

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.templates import template_names

runner = CliRunner()


def test_show_help_includes_examples():
    result = runner.invoke(app, ["show", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_list_templates_default_renders_every_name():
    result = runner.invoke(app, ["list", "templates"])
    assert result.exit_code == 0
    for name in template_names():
        assert name in result.stdout


def test_list_templates_json_returns_full_set():
    result = runner.invoke(app, ["list", "templates", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "list templates"
    assert payload["status"] == "ok"
    names = {t["name"] for t in payload["templates"]}
    assert names == set(template_names())


def test_show_template_dumps_raw_yaml_to_stdout():
    """CLI.3 (2026-06-02): templates rewritten to V2 shape; the body now
    declares `version: 1` + `tables[].columns` instead of V1 `masking_rules`.
    """
    result = runner.invoke(app, ["show", "template", "minimal"])
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed is not None
    assert parsed.get("version") == 2
    assert "tables" in parsed
    assert len(parsed["tables"]) >= 1
    assert len(parsed["tables"][0]["columns"]) >= 3


def test_show_template_each_bundled_template_parses_as_yaml():
    """Every bundled template must round-trip through PyYAML."""
    for name in template_names():
        result = runner.invoke(app, ["show", "template", name])
        assert result.exit_code == 0, f"{name} exited {result.exit_code}"
        parsed = yaml.safe_load(result.stdout)
        assert parsed is not None, f"{name} parsed to None"


def test_show_template_unknown_suggests_close_match():
    result = runner.invoke(app, ["show", "template", "hippa"])
    assert result.exit_code == 1
    assert "unknown template" in result.stderr.lower()
    assert "hipaa" in result.stderr  # did-you-mean


def test_show_template_json_envelope():
    result = runner.invoke(app, ["show", "template", "hipaa", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "show template"
    assert payload["status"] == "ok"
    assert payload["name"] == "hipaa"
    # CLI.3 (2026-06-02): V2 body uses `tables:` + `columns:` instead of
    # V1 `masking_rules:` flat list.
    assert "tables:" in payload["body"]


def test_show_template_quiet_produces_empty_stdout():
    result = runner.invoke(app, ["show", "template", "minimal", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_show_template_pipe_to_file_then_validate(tmp_path):
    """Smoke: dump a template, write it, validate it.

    Confirms the raw-YAML output is a valid pipeline as far as
    `decoy validate` is concerned.
    """
    for name in ("minimal", "hipaa", "pci", "gdpr"):
        result = runner.invoke(app, ["show", "template", name])
        assert result.exit_code == 0
        out = tmp_path / f"{name}.yaml"
        out.write_text(result.stdout, encoding="utf-8")
        validated = runner.invoke(app, ["validate", "config", str(out)])
        assert validated.exit_code == 0, f"{name} failed validate: {validated.output}"
