"""Tests for completer functions feeding tab completion."""

from __future__ import annotations

from decoy.cli import completers


def test_transform_ids_returns_known_set():
    ids = completers.transform_ids()
    assert "faker" in ids
    assert "hash" in ids
    assert "passthrough" in ids
    assert len(ids) >= 8


def test_disguise_ids_includes_default_and_hipaa():
    ids = completers.disguise_ids()
    # The engine ships at least these two bundles in the bones-only Disguises set.
    assert "default" in ids
    assert "hipaa" in ids


def test_faker_provider_ids_non_empty_and_strings():
    ids = completers.faker_provider_ids()
    assert all(isinstance(x, str) for x in ids)
    assert len(ids) > 0


def test_run_modes_matches_run_command_enum():
    """run_modes() must mirror the Mode enum that `decoy run --mode` accepts."""
    from decoy.cli.run import Mode

    assert set(completers.run_modes()) == {m.value for m in Mode}


def test_explain_topics_matches_explain_module():
    """explain_topics() must mirror the topic registry."""
    from decoy.cli.explain import topic_names

    assert completers.explain_topics() == topic_names()


def test_template_names_matches_templates_module():
    """template_names() must mirror the bundled template set."""
    from decoy.templates import template_names

    assert completers.template_names() == template_names()


def test_init_presets_match_template_names():
    """`decoy init --preset <Tab>` must offer every bundled template."""
    from decoy.templates import template_names

    assert completers.init_presets() == template_names()
