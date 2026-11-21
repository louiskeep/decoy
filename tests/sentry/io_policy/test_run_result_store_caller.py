"""L3a: `store_run_result` has exactly one caller outside the library package.

The run-result record stores the document `cli/run/_result.py` built, from the one place that
writes the envelope and the `--result` file. A second caller would store a second, differently
built document (ML3-rebuild).
"""

from __future__ import annotations

from tests.sentry.io_policy._store_callers import callers, scan


def test_store_run_result_has_exactly_one_caller() -> None:
    assert callers("store_run_result") == ["cli/run/_result.py"]


def test_the_scanner_sees_an_aliased_caller() -> None:
    """Mutation check: the same call under an alias, or through the module, is still a caller."""
    aliased = (
        "from decoy.cli.library import store_run_result as s\ndef f():\n    s({}, pipeline=None)\n"
    )
    through_module = "from decoy.cli import library\ndef f():\n    library.store_run_result({})\n"
    inside = "def f():\n    from decoy.cli.library import store_run_result as s\n    s()\n"
    assert scan(aliased, "store_run_result") == 1
    assert scan(through_module, "store_run_result") == 1
    assert scan(inside, "store_run_result") == 1
    assert scan("def f():\n    other()\n", "store_run_result") == 0
