"""User-facing text a first-time user reads: usage lines, explain topics, tips.

Each cell reproduces something a new user hit: a usage line naming a hidden
command, a topic quoting the wrong schema version, a tip naming presets that
`init` rejects, and a topic that hid that the token vault is plaintext.
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.explain import topic_names
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV, with_mask_secret

runner = CliRunner()


def _flat(text: str) -> str:
    """Collapse whitespace so assertions survive console wrapping."""
    return " ".join(text.split())


def _lines(text: str) -> list[str]:
    """Each output line without its panel border; inner spacing is kept."""
    return [line.strip(" │╭╰─") for line in text.splitlines()]


def _topic(name: str) -> dict:
    result = runner.invoke(app, ["explain", name, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


# --- Item 3: usage lines for the default-command groups ----------------------


@pytest.mark.parametrize(
    ("group", "argument", "missing"),
    [("scan", "SOURCE", "nofile.csv"), ("validate", "CONFIG", "nofile.yaml")],
)
def test_usage_error_names_the_group_not_the_hidden_command(
    tmp_path: Path, group: str, argument: str, missing: str
) -> None:
    result = runner.invoke(app, [group, str(tmp_path / missing)])

    assert result.exit_code == 2
    lines = _lines(result.output)
    assert f"Usage: decoy {group} [OPTIONS] {argument}" in lines
    assert f"Try 'decoy {group} --help' for help." in lines
    assert "_scan" not in result.output
    assert "_gate" not in result.output


@pytest.mark.parametrize(("group", "argument"), [("scan", "SOURCE"), ("validate", "CONFIG")])
def test_help_after_a_positional_shows_the_default_command_help(
    tmp_path: Path, group: str, argument: str
) -> None:
    target = tmp_path / "x.csv"
    target.write_text("a\n1\n")

    result = runner.invoke(app, [group, str(target), "--help"])

    assert result.exit_code == 0, result.output
    assert f"Usage: decoy {group} [OPTIONS] {argument}" in _lines(result.stdout)
    assert "_scan" not in result.stdout
    assert "_gate" not in result.stdout


def test_a_real_subcommand_keeps_its_own_usage_path() -> None:
    result = runner.invoke(app, ["validate", "config"])

    assert result.exit_code == 2
    assert "Usage: decoy validate config [OPTIONS] CONFIG" in _lines(result.output)


# --- Item 3: ticket ids and private paths in the text this slice owns --------

# Literal strings found in these surfaces by the first-user QA. The general
# pattern sentry over every user string is separate; these cells pin the fixes.
_REMOVED_FROM_TOPICS = ("FC-1", "storm-reframe", "S22-CL", "decoy-platform")


@pytest.mark.parametrize("name", topic_names())
def test_explain_topics_carry_no_ticket_ids_or_platform_paths(name: str) -> None:
    payload = _topic(name)
    text = payload["summary"] + "\n" + payload["body"]
    for removed in _REMOVED_FROM_TOPICS:
        assert removed not in text, f"{name!r} topic still says {removed!r}"


def test_init_help_carries_no_ticket_id() -> None:
    result = runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "OSS." not in result.stdout


@pytest.mark.parametrize("name", ["minimal", "generate", "hipaa"])
def test_templates_carry_no_ticket_ids_or_private_module_paths(name: str) -> None:
    result = runner.invoke(app, ["show", "template", name])

    assert result.exit_code == 0, result.output
    assert re.search(r"\b(CLI\.\d|SP-\d)", result.stdout) is None
    assert "decoy_engine.config._" not in result.stdout


def test_column_aware_init_header_points_at_explain_not_a_private_module(
    tmp_path: Path,
) -> None:
    source = tmp_path / "people.csv"
    source.write_text("id,city\n1,Austin\n2,Boston\n")
    out = tmp_path / "pipeline.yaml"

    result = runner.invoke(app, ["init", str(source), "--output", str(out), "--quiet"])

    assert result.exit_code == 0, result.output
    header = [line for line in out.read_text().splitlines() if line.startswith("#")]
    assert not any("decoy_engine." in line for line in header)
    assert any("decoy explain pipeline" in line for line in header)


# --- Item 4: the pipeline topic quotes the schema's version ------------------


def test_pipeline_topic_version_is_the_one_the_schema_accepts() -> None:
    from decoy_engine.config import PipelineConfig

    accepted = {str(v) for v in typing.get_args(PipelineConfig.model_fields["version"].annotation)}
    assert accepted, "PipelineConfig.version is no longer a Literal"

    body = _topic("pipeline")["body"]
    match = re.search(r"^\s*version\s+(\S+)", body, re.MULTILINE)

    assert match is not None, body
    assert match.group(1) in accepted


# --- Item 5: the disguise tip names presets init accepts ---------------------


def test_disguise_tip_points_init_at_the_template_list() -> None:
    result = runner.invoke(app, ["list", "disguises"])

    assert result.exit_code == 0, result.output
    text = _flat(result.stdout)
    assert "decoy list templates" in text
    assert "decoy explain disguises" in text
    assert "init --preset <id>" not in text


def test_every_listed_template_is_an_init_preset(tmp_path: Path) -> None:
    listed = runner.invoke(app, ["list", "templates", "--json"])
    assert listed.exit_code == 0, listed.output
    names = [t["name"] for t in json.loads(listed.stdout)["templates"]]
    assert names

    for name in names:
        out = tmp_path / f"{name}.yaml"
        result = runner.invoke(app, ["init", "--preset", name, "--output", str(out), "--quiet"])
        assert result.exit_code == 0, f"init --preset {name}: {result.output}"
        assert out.is_file()


# --- Item 11: the two vaults are told apart ----------------------------------


def test_tokenize_topic_says_the_token_vault_is_plaintext() -> None:
    body = _flat(_topic("tokenize")["body"])

    assert "plaintext" in body
    assert "0600" in body
    assert "run --vault" in body


def test_vault_topic_points_at_the_tokenize_store() -> None:
    body = _flat(_topic("vault")["body"])

    assert "decoy tokenize" in body


# --- Item 3: the old-engine mask-secret refusal, one text per surface -------------


@pytest.fixture
def old_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An engine with no keyprovider module, as the three surfaces' own probes see it.

    Only imports made from the CLI `run`, `tokenize` and `decoy.api` modules fail; the engine's
    own modules still import `keyprovider`, so the run reaches the surface probe.
    """
    import builtins

    real_import = builtins.__import__
    probing = {"decoy.cli.run", "decoy.cli.tokenize", "decoy.api"}

    def fake_import(name, globals=None, *args, **kwargs):
        if name == "decoy_engine.keyprovider" and (globals or {}).get("__name__") in probing:
            raise ImportError(name)
        return real_import(name, globals, *args, **kwargs)

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    (tmp_path / "people.csv").write_text("id\n1\n2\n")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {
            "people": {"type": "file", "format": "csv", "path": str(tmp_path / "people.csv")}
        },
        "tables": [
            {
                "name": "people",
                "columns": [{"name": "id", "strategy": "tokenize", "namespace": "pid"}],
            }
        ],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    config = tmp_path / "pipeline.yaml"
    config.write_text(yaml.safe_dump(with_mask_secret(cfg)), encoding="utf-8")
    return config


@pytest.mark.parametrize(
    ("command", "extra", "constant"),
    [
        ("run", [], "OLD_ENGINE_RUN"),
        ("tokenize", ["--vault", "tokens.db"], "OLD_ENGINE_TOKENIZE"),
    ],
)
def test_old_engine_refusal_is_the_registry_text_without_a_ticket_id(
    old_engine: Path, command: str, extra: list[str], constant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy import _mask_secret_guidance

    monkeypatch.chdir(old_engine.parent)
    result = runner.invoke(app, [command, str(old_engine), *extra])

    text = getattr(_mask_secret_guidance, constant)
    assert result.exit_code == EXIT_USAGE, result.output
    assert _flat(text) in _flat(result.output)
    assert "DE-0" not in result.output


def test_old_engine_refusal_for_mask_is_the_registry_text(old_engine: Path, tmp_path: Path) -> None:
    import pandas as pd

    import decoy
    from decoy import _mask_secret_guidance
    from decoy.api import MaskSecretConfigError

    with pytest.raises(MaskSecretConfigError) as caught:
        decoy.mask(pd.DataFrame({"id": [1, 2]}), str(old_engine), out=str(tmp_path / "o.csv"))

    assert str(caught.value) == _mask_secret_guidance.OLD_ENGINE_API
    assert "DE-0" not in str(caught.value)
