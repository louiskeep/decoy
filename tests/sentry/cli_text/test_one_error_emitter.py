"""D7 first inventory: the committed error-site baseline equals today's source, exactly.

``_error_sites`` recomputes every ``(path, function, expression fingerprint)`` error site under
``src/decoy``. This test requires that set to equal ``baselines/one-error-emitter.json`` in both
directions, so a new error site, a changed legacy error expression, or a baseline key added or
removed without the matching source change each fail. After this baseline merges, the ratchet
(``scripts/dev/ratchet_check.py``) holds it shrink-only against its merge-base copy.
"""

from __future__ import annotations

import json

import pytest
from tests.sentry.cli_text import _error_sites as sites

BASELINE = sites.ROOT / "tests" / "sentry" / "baselines" / "one-error-emitter.json"
REGISTRY = sites.ROOT / "scripts" / "dev" / "sentry_registry.toml"


def _recorded() -> set[str]:
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["entries"])


def test_baseline_equals_the_source_inventory() -> None:
    live, recorded = sites.inventory(), _recorded()
    assert live - recorded == set(), "error sites missing from the baseline (use emit_error)"
    assert recorded - live == set(), "stale baseline entries (shrink the baseline)"


def test_baseline_is_registered_as_cl0() -> None:
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert doc["sentry_id"] == "one-error-emitter"
    assert doc["created_in"] == "CL0"
    assert 'id = "one-error-emitter"' in REGISTRY.read_text(encoding="utf-8")


def _keys(src: str) -> set[str]:
    return sites.sites_in_source(src, "cli/x.py")


@pytest.mark.parametrize(
    "src",
    [
        "def f(state):\n    state.err_console.print(error('error:'), 'm')\n",
        "def f():\n    err_console.print(error('error:'), 'm')\n",
        "def f(state):\n    state.err_console.print(output.error('fail:'), 'm', markup=False)\n",
        "def f(state):\n    state.err_console.print('x', error('e'))\n",
        "def f():\n    emit({'command': 'c', 'status': 'error', 'error': 'm'})\n",
        "def f():\n    emit({'status': 'error'})\n",
        "def f():\n    emit(dict(command='c', status='error', error='m'))\n",
        "X = {'status': 'error'}\n",
        "class C:\n    def f(self, state):\n        state.err_console.print(error('e'), 'm')\n",
    ],
)
def test_every_spelling_is_seen(src: str) -> None:
    assert len(_keys(src)) == 1


@pytest.mark.parametrize(
    "src",
    [
        "def f(state):\n    state.console.print(error('e'), 'm')\n",
        "def f(state):\n    state.err_console.print('plain')\n",
        "def f():\n    emit({'status': 'ok'})\n",
        "def f():\n    emit(dict(status='ok'))\n",
        "def f():\n    other(status='error')\n",
    ],
)
def test_non_error_constructions_are_not_sites(src: str) -> None:
    assert _keys(src) == set()


def test_key_names_the_enclosing_scope() -> None:
    src = "class C:\n    def f(self, s):\n        s.err_console.print(error('e'), 'm')\n"
    (key,) = _keys(src)
    assert key.startswith("cli/x.py::C.f::")
    (module_key,) = _keys("X = {'status': 'error'}\n")
    assert module_key.startswith("cli/x.py::<module>::")


def test_a_moved_site_keeps_its_key_and_an_edited_one_changes_it() -> None:
    base = "def f(s):\n    s.err_console.print(error('e'), 'm')\n"
    moved = "\n\n# note\ndef f(s):\n    s.err_console.print(  error('e'),\n 'm')\n"
    edited = "def f(s):\n    s.err_console.print(error('e'), 'other')\n"
    assert _keys(base) == _keys(moved)
    assert _keys(base) != _keys(edited)


def test_identical_sites_in_one_function_are_both_counted() -> None:
    src = (
        "def f(s, a):\n"
        "    if a:\n        s.err_console.print(error('e'), 'm')\n"
        "    s.err_console.print(error('e'), 'm')\n"
    )
    assert len(_keys(src)) == 2


def test_growth_is_caught_even_when_the_baseline_gains_the_key() -> None:
    """Mutation shape: a new site plus its fingerprint added to the baseline still moves the
    inventory away from the source of record only if the source lacks it, so the equality
    guard alone cannot be satisfied by editing the baseline."""
    new = "def g(s):\n    s.err_console.print(error('error:'), 'new')\n"
    added = _keys(new)
    assert len(added) == 1
    assert added.isdisjoint(sites.inventory())
    assert (_recorded() | added) != sites.inventory()
