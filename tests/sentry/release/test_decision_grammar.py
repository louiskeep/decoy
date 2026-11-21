"""One dated-owner-decision grammar: the ratchet and release_identity give the same answers.

`tests/sentry/_ratchet.py` loads `is_dated_owner_decision` from `release_identity.py`, so a
corpus run through both callers must agree. Existing `approved_growth` rows stay valid.
"""

from __future__ import annotations

import pytest
from tests.sentry import _ratchet

from decoy.distribution import release_identity

GOOD = [
    "owner 2026-11-20 W3 pipeline file suffix allow entry",
    "owner 2026-11-18: V1 bundles are GitHub Release assets",
    "owner 2024-02-29 leap day is a real day",
]
BAD = [
    "",
    "owner",
    "owner 2026-11-18",
    "owner 2026-11-18 short",
    "owner 2026-13-40 bad calendar date here",
    "owner 2026-11-18:no space after colon here",
    "Owner 2026-11-18 wrong case of the word owner",
    "owner 2026-11-18 text with trailing newline\n",
    "2026-11-18 owner missing prefix word text",
    None,
    42,
]


@pytest.mark.parametrize("text", GOOD)
def test_good_decisions_pass_both_callers(text):
    assert release_identity.is_dated_owner_decision(text)
    assert _ratchet._decision_ok(text)


@pytest.mark.parametrize("text", BAD)
def test_bad_decisions_fail_both_callers(text):
    assert not release_identity.is_dated_owner_decision(text)
    assert not _ratchet._decision_ok(text)
