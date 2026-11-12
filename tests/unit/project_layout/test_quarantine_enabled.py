"""`quarantine_enabled`: the one reader of "is quarantine on" for a config dict."""

from __future__ import annotations

import pytest

from decoy.cli.io import quarantine_enabled


@pytest.mark.parametrize(
    ("cfg", "expected"),
    [
        (None, False),
        ("quarantine", False),
        (["quarantine"], False),
        ({}, False),
        ({"quarantine": None}, False),
        ({"quarantine": True}, False),
        ({"quarantine": ["enabled"]}, False),
        ({"quarantine": {}}, False),
        ({"quarantine": {"output_path": "q.csv"}}, False),
        ({"quarantine": {"enabled": False}}, False),
        ({"quarantine": {"enabled": True}}, True),
        # Truthiness, not type: the engine's schema check owns the value's type, so the
        # string "false" reads as on here.
        ({"quarantine": {"enabled": "false"}}, True),
    ],
)
def test_quarantine_enabled(cfg: object, expected: bool) -> None:
    assert quarantine_enabled(cfg) is expected
