"""L3a: `store_evidence` has exactly one caller outside the library package (amendment 2026-11-12).

Until RESULT C1a and C1b land, the evidence record is stored where the manifest is built,
`cli/run/_evidence.py`; `finish` takes the call over in the RESULT PR. A second caller would
store a second, differently built manifest (ML3-drift).
"""

from __future__ import annotations

from tests.sentry.io_policy._store_callers import callers, scan


def test_store_evidence_has_exactly_one_caller() -> None:
    assert callers("store_evidence") == ["cli/run/_evidence.py"]


def test_the_scanner_sees_an_aliased_caller() -> None:
    """Mutation check: the same call under an alias, or through the module, is still a caller."""
    aliased = (
        "from decoy.cli.library import store_evidence as s\ndef f():\n    s({}, pipeline=None)\n"
    )
    through_module = "from decoy.cli import library\ndef f():\n    library.store_evidence({})\n"
    inside = "def f():\n    from decoy.cli.library import store_evidence as s\n    s()\n"
    assert scan(aliased, "store_evidence") == 1
    assert scan(through_module, "store_evidence") == 1
    assert scan(inside, "store_evidence") == 1
    assert scan("def f():\n    other()\n", "store_evidence") == 0
