"""Every committed baseline or allowlist a CLI sentry reads is registered and checked once.

The ratchet only protects what ``sentry_registry.toml`` names. Each registry row has a ``kind``:
``json`` rows are read by their sentry through ``load_allowlist`` (the baseline is the only copy);
``from_scan`` and ``from_file`` rows are tied to their reader's live keys, both directions. Every
baseline header is checked here once, with its exact ``created_in``. Every ``json`` row names its
``consumer`` file, and that file is the only one that calls ``load_allowlist("<id>")``, so a split
or rename cannot leave an unused old row behind a new one. Every sentry and helper module under
``tests/sentry`` (and the ``tests/unit`` sentries) that holds an inline allowlist-shaped constant,
or reads a committed data file that is not registered, fails, so a new allowlist cannot sit
beside the ratchet. The temporary snapshot proof of the allowlist move (``allowlist-before.json``)
lives here too and goes in C-G2.

Ported from decoy-engine ``tests/sentry/test_baseline_registry.py`` (X0a).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
from tests.sentry._ratchet import load_allowlist

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _baseline_sources as bs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

LIST_NAME = re.compile(r"ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS|OMIT", re.IGNORECASE)
COLLECTION_CALLS = frozenset({"frozenset", "set", "tuple", "list", "dict"})
DATA_LITERAL = re.compile(r"[\w.\-]+\.(?:json|toml)$")
SENTRIES: tuple[str, ...] = bs.load_module(bs.SENTRY / "test_sentry_manifest.py").SENTRIES


# The slice that first recorded each baseline. A rewritten header is a change to review.
CREATED_IN = {
    "engine-internal-allow": "X0a",
    "root-help-omitted": "X0a",
    "readme-table-omitted": "X0a",
    "atomic-writer-allow": "L1b.1",
    "gate-single-entry-allow": "VALIDATE-ALWAYS-P1",
    "csv-read-allow": "CLI-DIALECT-C",
    "scan-call-allow": "FREEZE-ITEM3-C1",
    "target-writes-allow": "CLI-FMT-A2",
    "manifest-path-forward-allow": "PROJECT-LAYOUT-P3",
    "output-placement-allow": "PROJECT-LAYOUT-P2b",
    "output-name-allow": "PROJECT-LAYOUT-P2b",
    "config-route-allow": "VALUE-FREE-ERRORS-A3",
    "exception-context": "B2",
    "private-file-sinks": "X7c-S3",
    "engine-reason-code-copies": "GEN-CLI-C2",
    "module-size": "LAYOUT-C2",
    "package-fanout": "LAYOUT-C2",
    "import-layers": "LAYOUT-C3",
    "canonical-json-allow": "L1b.2",
    "library-writer-allow": "L1b.2",
    "kind-canary-pending": "L1c.2",
    "one-error-emitter": "CL0",
    "run-exit-owners": "RESULT-C-DOC2",
    "run-exit-owners-io": "SCAN-ML-C2a",
    "env-reads": "CL2",
    "json-stdout-writes": "CL2",
    "exit-code-owner": "CL3",
    "config-load-allow": "CL3",
    "retired-name-pending": "NAME-REMOVAL-C1",
    "banned-text-allow": "PROP-C-G1",
    "outbound-network-owners": "FREEZE-S6",
    "old-org-refs": "CLI-REL-S0id",
}
SNAPSHOT = json.loads(
    (bs.SENTRY / "allowlist-before.json").read_text(encoding="utf-8")
)  # the allowlists before the move, taken from the code


def registry_rows() -> list[dict[str, str]]:
    text = bs.REGISTRY.read_text(encoding="utf-8")
    return list(tomllib.loads(text).get("sentry", []))


def registry() -> dict[str, str]:
    return {r["id"]: r["baseline"] for r in registry_rows()}


def _doc(sentry_id: str) -> dict[str, object]:
    path = bs.ROOT / registry()[sentry_id]
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.mark.parametrize("row", registry_rows(), ids=lambda r: r["id"])
def test_every_baseline_has_its_header_and_file_name(row: dict[str, str]) -> None:
    """The one header check: ``sentry_id`` is the registry id and ``created_in`` is named."""
    assert row["baseline"] == f"tests/sentry/baselines/{row['id']}.json"
    assert row.get("kind") in bs.KINDS, "registry row has no known kind"
    doc = _doc(row["id"])
    assert doc["sentry_id"] == row["id"]
    assert doc["created_in"] == CREATED_IN[row["id"]]


def test_created_in_table_covers_every_row_and_no_other() -> None:
    assert set(CREATED_IN) == {r["id"] for r in registry_rows()}


@pytest.mark.parametrize("sentry_id", sorted(SNAPSHOT))
def test_loaded_allowlist_equals_the_snapshot_taken_before_the_move(sentry_id: str) -> None:
    """Temporary (C-G2 deletes it): the move into the baselines changed no value."""
    assert load_allowlist(sentry_id) == SNAPSHOT[sentry_id]


def test_only_recomputed_sentries_have_a_reader() -> None:
    kinds = {r["id"]: r["kind"] for r in registry_rows()}
    assert {i for i, k in kinds.items() if k != "json"} == set(bs.READERS)


@pytest.mark.parametrize("sentry_id", sorted(bs.READERS))
def test_recomputed_keys_match_the_registered_baseline(sentry_id: str) -> None:
    live, recorded = bs.READERS[sentry_id](), set(_doc(sentry_id)["entries"])  # type: ignore[call-overload]
    assert live - recorded == set(), "live entries missing from the baseline"
    assert recorded - live == set(), "stale baseline entries (shrink the baseline)"


def _is_collection(value: ast.expr | None) -> bool:
    if isinstance(value, ast.Call):
        return isinstance(value.func, ast.Name) and value.func.id in COLLECTION_CALLS
    return isinstance(value, (ast.Dict, ast.Tuple, ast.List, ast.Set))


_WRAPPERS = frozenset({"frozenset", "set", "tuple", "list", "sorted", "dict"})
_VIEWS = frozenset({"items", "keys", "values"})


def _is_loader_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_allowlist"
    )


def _from_the_baseline_only(node: ast.expr) -> bool:
    """Whether every entry of the value comes from ``load_allowlist`` and nothing else.

    Accepted: the bare call or one of its ``.items()``/``.keys()``/``.values()`` views; a wrapper
    (``frozenset``, ``set``, ``tuple``, ``list``, ``sorted``, ``dict``) with one such argument;
    a comprehension with one generator over such a source. Anything with literal elements, a
    ``*`` or ``**`` unpack or an operator is a second copy.
    """
    if _is_loader_call(node):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _VIEWS:
            return not node.args and _is_loader_call(func.value)
        if isinstance(func, ast.Name) and func.id in _WRAPPERS:
            return (
                len(node.args) == 1 and not node.keywords and _from_the_baseline_only(node.args[0])
            )
        return False
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        return len(node.generators) == 1 and _from_the_baseline_only(node.generators[0].iter)
    return False


def _combines_entries(value: ast.expr | None) -> bool:
    """An operator expression (``a | b``, ``a + b``) that mixes the loader or a collection in.

    A plain path join such as ``ROOT / "tests" / "x.json"`` has neither and is not shaped.
    """
    if not isinstance(value, ast.BinOp):
        return False
    return any(
        _is_loader_call(n) or _is_collection(n) for n in ast.walk(value) if isinstance(n, ast.expr)
    )


def inline_allowlists(sources: dict[str, str], closed: set[tuple[str, str]]) -> list[str]:
    """Allowlist-shaped module constants that hold their own entries instead of the baseline."""
    found = []
    for name, text in sources.items():
        for node in ast.parse(text).body:
            targets = (
                node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            )
            value = getattr(node, "value", None)
            for t in targets:
                is_list = isinstance(t, ast.Name) and LIST_NAME.search(t.id)
                shaped = _is_collection(value) or _combines_entries(value)
                if (
                    is_list
                    and shaped
                    and not _from_the_baseline_only(value)
                    and (name, t.id) not in closed
                ):
                    found.append(f"{name}: constant {t.id}")
    return sorted(set(found))


def unregistered_data_files(
    sources: dict[str, str], data_files: set[str], covered_files: set[str]
) -> list[str]:
    """Committed data files a sentry reads that no registry row or reader names.

    Files are identified by repo-relative path. A literal that names a file name shared by
    several data files is flagged unless every one of them is covered.
    """
    by_name: dict[str, set[str]] = {}
    for path in data_files:
        by_name.setdefault(path.rsplit("/", 1)[-1], set()).add(path)
    found = []
    for name, text in sources.items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                base = node.value.rsplit("/", 1)[-1]
                if DATA_LITERAL.fullmatch(base) and not by_name.get(base, set()) <= covered_files:
                    found.append(f"{name}: data file {base}")
    return sorted(set(found))


def _covered_files() -> set[str]:
    return set(registry().values()) | set(bs.DATA_FILES)


def _data_files() -> set[str]:
    return {
        p.relative_to(bs.ROOT).as_posix()
        for root in ("tests", "docs")
        for p in (bs.ROOT / root).rglob("*")
        if p.suffix in {".json", ".toml"}
    }


def _scanned_sources() -> dict[str, str]:
    """Every sentry and helper module under ``tests/sentry``, plus the ``tests/unit`` sentries.

    Keyed by repo-relative path. This file holds the seeded fixtures below and is left out.
    """
    paths = {p.relative_to(bs.ROOT).as_posix() for p in (bs.SENTRY).rglob("*.py")}
    paths |= {s for s in SENTRIES if not s.startswith("tests/sentry/")}
    paths -= {"tests/sentry/test_baseline_registry.py"}
    return {p: (bs.ROOT / p).read_text(encoding="utf-8") for p in sorted(paths)}


def test_the_scan_reaches_helper_modules_and_the_tests_unit_sentries() -> None:
    sources = _scanned_sources()
    unit = {s for s in SENTRIES if s.startswith("tests/unit/")}
    assert len(unit) == 3
    assert unit <= set(sources)
    assert "tests/sentry/cli_text/_banned_text.py" in sources


def test_no_sentry_holds_an_inline_allowlist() -> None:
    assert inline_allowlists(_scanned_sources(), set(bs.NOT_A_LIST_CONSTS)) == []


def test_no_sentry_reads_an_unregistered_baseline() -> None:
    assert unregistered_data_files(_scanned_sources(), _data_files(), _covered_files()) == []


def test_not_a_list_consts_still_exist() -> None:
    sources = _scanned_sources()
    stale = [
        f"{f}: {c}"
        for f, c in bs.NOT_A_LIST_CONSTS
        if not re.search(rf"^{c}\b", sources.get(f, ""), re.MULTILINE)
    ]
    assert stale == []


def loader_calls(sources: dict[str, str]) -> tuple[set[tuple[str, str]], list[str]]:
    """``(file, id)`` of each ``load_allowlist("<id>")`` call, and calls with a non-literal id."""
    calls: set[tuple[str, str]] = set()
    bad: list[str] = []
    for path, text in sources.items():
        for node in ast.walk(ast.parse(text)):
            if not (isinstance(node, ast.Call) and _is_loader_call(node)):
                continue
            arg = node.args[0] if len(node.args) == 1 and not node.keywords else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                calls.add((path, arg.value))
            else:
                bad.append(f"{path}:{node.lineno}")
    return calls, sorted(bad)


def consumer_findings(
    consumers: dict[str, str], calls: set[tuple[str, str]], bad: list[str]
) -> list[str]:
    """Why the ``json`` rows (``{id: consumer file}``) and the loader calls do not match 1:1."""
    out = [f"{where}: load_allowlist needs one literal sentry id" for where in bad]
    wanted = {(file, sid) for sid, file in consumers.items()}
    out += [f"{f}: reads unregistered or foreign id {i}" for f, i in sorted(calls - wanted)]
    out += [f"{i}: row's consumer {f} never loads it" for f, i in sorted(wanted - calls)]
    return out


def _json_consumers() -> dict[str, str]:
    rows = [r for r in registry_rows() if r["kind"] == "json"]
    assert all(r.get("consumer") for r in rows), "a json row has no consumer file"
    assert not [r["id"] for r in registry_rows() if r["kind"] != "json" and "consumer" in r]
    return {r["id"]: r["consumer"] for r in rows}


def test_every_json_row_is_loaded_by_its_consumer_and_by_no_one_else() -> None:
    sources = _scanned_sources()
    consumers = _json_consumers()
    assert all(f in sources for f in consumers.values()), "a consumer file is not scanned"
    calls, bad = loader_calls(sources)
    assert consumer_findings(consumers, calls, bad) == []


def test_a_retargeted_sentry_with_a_new_row_and_the_old_row_kept_is_caught() -> None:
    """The laundering route: the sentry loads a new id, the old id stays registered."""
    consumers = {"old-allow": "tests/sentry/test_x.py", "new-allow": "tests/sentry/test_x.py"}
    calls = {("tests/sentry/test_x.py", "new-allow")}
    assert consumer_findings(consumers, calls, []) == [
        "old-allow: row's consumer tests/sentry/test_x.py never loads it"
    ]


def test_a_loader_call_for_an_unregistered_or_foreign_id_is_caught() -> None:
    consumers = {"a-allow": "tests/sentry/test_a.py"}
    calls = {("tests/sentry/test_a.py", "a-allow"), ("tests/sentry/test_b.py", "a-allow")}
    assert consumer_findings(consumers, calls, []) == [
        "tests/sentry/test_b.py: reads unregistered or foreign id a-allow"
    ]


def test_a_non_literal_loader_id_is_caught() -> None:
    calls, bad = loader_calls({"tests/sentry/test_a.py": "X = load_allowlist(name)\n"})
    assert calls == set()
    assert consumer_findings({}, calls, bad) == [
        "tests/sentry/test_a.py:1: load_allowlist needs one literal sentry id"
    ]


@pytest.mark.parametrize(
    "seed",
    [
        'NEW_ALLOWLIST = {"a": "b"}',
        'NEW_ALLOWLIST = frozenset({"bypass::site"})',
        'NEW_ALLOWLIST = set(["a"])',
        'NEW_ALLOWLIST = tuple(["a"])',
        'NEW_ALLOWLIST = list(("a",))',
        'NEW_ALLOWLIST = ("a",)',
        'NEW_ALLOWLIST = {"a"}',
        'NEW_ALLOWLIST: frozenset[str] = frozenset({"a"})',
        '_NEW_OMITTED = frozenset({"a"})',
        '_ALLOWED: dict[str, str] = {"a": "b"}',
        'NEW_ALLOWLIST = {**load_allowlist("csv-read-allow"), "cli/new.py::f": {"reason": "x"}}',
        'NEW_ALLOWLIST = frozenset(set(load_allowlist("x")) | {"extra"})',
        'NEW_ALLOWLIST = (*load_allowlist("x"), "extra")',
        'NEW_ALLOWLIST = load_allowlist("x") | {"extra": {}}',
        'NEW_ALLOWLIST = tuple(load_allowlist("x")) + ("extra",)',
        "NEW_ALLOWLIST = dict(a=1)",
        '_allowed = {"a": "b"}',
    ],
)
def test_seeded_inline_allowlists_are_caught(seed: str) -> None:
    name = seed.split(" ", 1)[0].rstrip(":")
    found = inline_allowlists({"tests/sentry/_helper.py": seed + "\n"}, set(bs.NOT_A_LIST_CONSTS))
    assert found == [f"tests/sentry/_helper.py: constant {name}"]


@pytest.mark.parametrize(
    "seed",
    [
        'ALLOWLIST = tuple(Row(k, e["reason"]) for k, e in load_allowlist("x").items())',
        'ALLOWLIST = frozenset(load_allowlist("x"))',
        'ALLOWLIST = tuple(sorted(load_allowlist("x")))',
        'ALLOWLIST = {k: e["max"] for k, e in load_allowlist("x").items()}',
        'ALLOWLIST = [Row(*k.split("::")) for k in load_allowlist("x")]',
    ],
)
def test_an_allowlist_built_only_from_the_baseline_passes(seed: str) -> None:
    assert inline_allowlists({"test_new.py": seed + "\n"}, set()) == []


def test_seeded_unregistered_readers_are_caught() -> None:
    seeded_file = {"test_new.py": 'P = ROOT / "tests" / "fixtures" / "fresh-list.json"\n'}
    data = {"tests/fixtures/fresh-list.json"}
    assert unregistered_data_files(seeded_file, data, _covered_files()) == [
        "test_new.py: data file fresh-list.json"
    ]


def test_a_registered_data_file_passes_and_an_unregistered_one_is_caught() -> None:
    files = _covered_files()
    assert "tests/sentry/io_policy/file_sinks.toml" in files
    sinks = {"tests/sentry/io_policy/file_sinks.toml"}
    registered = {"test_new.py": 'P = HERE / "file_sinks.toml"\n'}
    assert unregistered_data_files(registered, sinks, files) == []
    other = {"tests/sentry/io_policy/other_sinks.toml"}
    unregistered = {"test_new.py": 'P = HERE / "other_sinks.toml"\n'}
    assert unregistered_data_files(unregistered, other, files) == [
        "test_new.py: data file other_sinks.toml"
    ]


def test_a_same_named_unregistered_file_is_not_hidden_by_a_registered_one() -> None:
    files = _covered_files()
    both = {"tests/sentry/baselines/env-reads.json", "tests/fixtures/env-reads.json"}
    source = {"test_new.py": 'P = HERE / "env-reads.json"\n'}
    assert unregistered_data_files(source, both, files) == ["test_new.py: data file env-reads.json"]


def test_a_helper_module_holding_an_allowlist_is_caught() -> None:
    helper = {"tests/sentry/cli_text/_helper.py": 'ALLOWLIST = {("a", "b"): (1, "why")}\n'}
    assert inline_allowlists(helper, set()) == [
        "tests/sentry/cli_text/_helper.py: constant ALLOWLIST"
    ]
