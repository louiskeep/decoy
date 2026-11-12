"""Class 3 sentry: no new ``raise ... from None`` inside an ``except`` block under ``src/decoy``.

``from None`` hides the cause but keeps ``__context__`` (PEP 415), so it neither helps a reader
nor makes a message value-free. The count is a shrink-only ratchet, one baseline key per site
(``path::qualified function::ordinal``), taken on the B2 base. The bulk hoists are V2 corrective
work; a new site fails here, and a removed site must leave the baseline. The scan is the
engine's vendored ``_defect_scan.py``. The CLI has no private module behind a public facade, so
the engine's class 6 facade cell has nothing to check here.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tests.sentry.defects import _defect_scan as scan

SRC = scan.ROOT / "src" / "decoy"
BASELINE = Path(__file__).resolve().parents[1] / "baselines" / "exception-context.json"


def _baseline() -> dict[str, dict[str, str]]:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["sentry_id"] == "exception-context"
    return data["entries"]  # type: ignore[no-any-return]


# The ratchet's keys, read by tests/sentry/_baseline_sources.py; they live in the baseline only.
BASELINE_KEYS: tuple[str, ...] = tuple(sorted(_baseline()))


def _keys(source: str, rel: str = "decoy/x.py") -> list[str]:
    return scan.from_none_tree_keys(ast.parse(source), rel)


# ----- the real tree ------------------------------------------------------------------------


def test_no_new_raise_from_none_inside_an_except_block() -> None:
    found = set(scan.from_none_keys(scan.ModuleIndex(SRC)))
    new = sorted(found - set(BASELINE_KEYS))
    assert not new, f"new `raise ... from None` inside an except block (hoist it): {new}"


def test_the_baseline_only_lists_sites_that_still_exist() -> None:
    found = set(scan.from_none_keys(scan.ModuleIndex(SRC)))
    stale = sorted(set(BASELINE_KEYS) - found)
    assert not stale, f"sites were removed or hoisted; delete these baseline keys: {stale}"


# ----- seeded cells -------------------------------------------------------------------------


def test_a_raise_from_none_in_a_handler_is_counted() -> None:
    src = "def f():\n    try:\n        g()\n    except ValueError:\n        raise E() from None\n"
    assert _keys(src) == ["decoy/x.py::f::0"]


def test_ordinals_count_per_function_and_nested_handlers_count_once() -> None:
    src = (
        "def f():\n"
        "    try:\n        a()\n    except A:\n"
        "        try:\n            b()\n        except B:\n            raise E() from None\n"
        "        raise F() from None\n"
        "class C:\n"
        "    def m(self):\n"
        "        try:\n            a()\n        except A:\n            raise E() from None\n"
    )
    assert _keys(src) == ["decoy/x.py::f::0", "decoy/x.py::f::1", "decoy/x.py::C.m::0"]


@pytest.mark.parametrize(
    "src",
    [
        "def f():\n    raise E() from None\n",
        "def f():\n    try:\n        a()\n    except A as e:\n        raise E() from e\n",
        "def f():\n    try:\n        a()\n    except A:\n        raise E()\n",
        "def f():\n    try:\n        a()\n    except A:\n        pass\n    raise E() from None\n",
    ],
)
def test_forms_that_are_not_the_class_are_not_counted(src: str) -> None:
    assert _keys(src) == []


def test_adding_one_site_to_a_real_module_is_detected(tmp_path: Path) -> None:
    real = (SRC / "ci" / "manifest.py").read_text(encoding="utf-8")
    pkg = tmp_path / "decoy" / "ci"
    pkg.mkdir(parents=True)
    planted = (
        real
        + "\n\ndef _planted():\n    try:\n        pass\n    except OSError:\n        raise ValueError() from None\n"
    )
    (pkg / "manifest.py").write_text(planted, encoding="utf-8")
    found = set(scan.from_none_keys(scan.ModuleIndex(tmp_path / "decoy")))
    assert found - set(BASELINE_KEYS) == {"decoy/ci/manifest.py::_planted::0"}
