"""D7 first inventory: the committed error-site baseline equals today's source, exactly.

``_error_sites`` recomputes every ``(path, function, expression fingerprint)`` error site under
``src/decoy``. This test requires that set to equal ``baselines/one-error-emitter.json`` in both
directions, so a new error site, a changed legacy error expression, or a baseline key added or
removed without the matching source change each fail. After this baseline merges, the ratchet
(``scripts/dev/ratchet_check.py``) holds it shrink-only against its merge-base copy.
"""

from __future__ import annotations

import ast
import json
import re

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


# --- the owner, and the shape of every literal still on the baseline -------------------------

FIXED = {"command", "status", "error", "code", "hint"}
CODE = re.compile(r"[a-z][a-z0-9_.]*")


def test_the_owner_is_not_a_site_but_a_namesake_elsewhere_is() -> None:
    src = "def emit_error(s):\n    s.err_console.print(error('error:'), 'm')\n"
    assert sites.sites_in_source(src, "ui/output.py") == set()
    assert len(sites.sites_in_source(src, "cli/x.py")) == 1
    other = "def other(s):\n    s.err_console.print(error('error:'), 'm')\n"
    assert len(sites.sites_in_source(other, "ui/output.py")) == 1


def _literal_problems(node: ast.Dict | ast.Call) -> list[str]:
    """Why one error literal does not fit decoy-error-v1, or an empty list."""
    if isinstance(node, ast.Dict):
        members = {
            k.value: v
            for k, v in zip(node.keys, node.values, strict=True)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
    else:
        members = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
    problems = [f"missing {name}" for name in ("command", "error") if name not in members]
    if "message" in members:
        problems.append("carries message")
    code = members.get("code")
    if isinstance(code, ast.Constant) and not (
        isinstance(code.value, str) and CODE.fullmatch(code.value)
    ):
        problems.append("code fails the pattern")
    for name, value in members.items():
        if name not in FIXED and not _json_typed(value):
            problems.append(f"{name} is not JSON-typed")
    return problems


def _json_typed(node: ast.expr) -> bool:
    """A literal that is not JSON is refused. A name or call is judged at its own site."""
    if isinstance(node, (ast.Set, ast.SetComp)):
        return False
    if isinstance(node, ast.Constant):
        return node.value is None or isinstance(node.value, (bool, int, float, str))
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_json_typed(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_json_typed(v) for v in node.values)
    return True


def test_every_retained_error_literal_fits_the_schema() -> None:
    bad: dict[str, list[str]] = {}
    for path in sorted(sites.SRC.rglob("*.py")):
        rel = path.relative_to(sites.SRC).as_posix()
        for node in sites.error_literals(path.read_text(encoding="utf-8")):
            if problems := _literal_problems(node):
                bad[f"{rel}:{node.lineno}"] = problems
    assert bad == {}


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("{'status': 'error', 'error': 'm'}", "missing command"),
        ("{'command': 'c', 'status': 'error'}", "missing error"),
        ("{'command': 'c', 'status': 'error', 'error': 'm', 'message': 'm'}", "carries message"),
        ("{'command': 'c', 'status': 'error', 'error': 'm', 'code': 'Bad Code'}", "code fails"),
        ("{'command': 'c', 'status': 'error', 'error': 'm', 'tags': {'a'}}", "tags is not JSON"),
        ("{'command': 'c', 'status': 'error', 'error': 'm', 'raw': b'x'}", "raw is not JSON"),
        ("dict(command='c', status='error', message='m')", "missing error"),
    ],
)
def test_a_literal_that_breaks_the_schema_is_reported(src: str, expected: str) -> None:
    (node,) = sites.error_literals(src)
    assert any(expected in p for p in _literal_problems(node))


def test_list_and_object_context_is_accepted() -> None:
    src = (
        "{'command': 'run', 'status': 'error', 'error': 'm', 'code': 'a.b_c',"
        " 'outputs': [{'n': 1}], 'extra': {'k': ['v', None, 1.5, True]}}"
    )
    (node,) = sites.error_literals(src)
    assert _literal_problems(node) == []


def test_a_new_direct_call_and_a_new_hand_built_object_are_gained_sites() -> None:
    recorded = _recorded()
    human = _keys("def new(s):\n    s.err_console.print(error('error:'), 'x')\n")
    built = _keys("def new(s):\n    emit_json(s, {'command': 'c', 'status': 'error', 'error': 'x'})\n")
    assert len(human) == len(built) == 1
    assert (human | built) - recorded == human | built
