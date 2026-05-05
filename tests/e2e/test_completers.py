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
