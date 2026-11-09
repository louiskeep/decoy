"""AT-S3: every ``--json`` envelope ``command`` value names a command the user can type.

A literal copied from an old mount point (``"compile explain"`` after the command moved under
``validate``) stays wrong with no test noticing. This reads the Click tree at test time and
checks, by AST over ``src/decoy/cli/**``, every string that becomes an envelope ``command``:

* dict literals with the key ``"command"``, ``dict(command=...)``, ``x.update(command=...)`` and
  ``x.setdefault("command", ...)``;
* subscript assignments ``envelope["command"] = "..."`` (annotated or not);
* the call-site literals of the named forwarders in ``FORWARDERS`` (a helper that takes the
  command name as an argument and puts it in the envelope).

A value is valid when its longest prefix that is a visible Click path (with or without a leading
``decoy``) is followed by nothing, or, for ``list`` and ``show`` only, by one kind from that
command's own registry. Hidden paths (``scan _scan``, ``validate _gate``) do not count. A
non-literal at any other site fails; ``FORWARDERS`` is the only escape.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tests.command_tree import visible_paths
from tests.sentry.io_policy._calls import sites

from decoy.cli.reference import _LIST_KINDS, _SHOW_KINDS

CLI_DIR = Path(__file__).resolve().parents[3] / "src" / "decoy" / "cli"

# Qualified target -> (parameter name, positional index, expected call sites in src/decoy/cli).
# Calls are resolved with the shared import resolver (`tests/sentry/io_policy/_calls.py`), so an
# aliased import, a module-alias attribute call and a bare same-file call all count. The pinned
# count turns a missed caller red.
FORWARDERS: dict[str, tuple[str, int, int]] = {
    "decoy.cli.report._load_manifest": ("command", 2, 5),
    "decoy.cli.scan._emit_load_error": ("command_name", 3, 4),
    "decoy.cli.reference._reject_kind": ("verb", 99, 2),
}

KIND_REGISTRIES = {"list": set(_LIST_KINDS), "show": set(_SHOW_KINDS)}


def is_valid(value: str, paths: set[tuple[str, ...]]) -> bool:
    tokens = value.split()
    if tokens[:1] == ["decoy"]:
        tokens = tokens[1:]
    for cut in range(len(tokens), 0, -1):
        if tuple(tokens[:cut]) in paths:
            rest = tokens[cut:]
            if not rest:
                return True
            registry = KIND_REGISTRIES.get(tokens[0]) if cut == 1 else None
            return registry is not None and len(rest) == 1 and rest[0] in registry
    return False


def _is_command_key(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "command"


def _call_name(call: ast.Call) -> str | None:
    fn = call.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None


def _module(rel: str) -> str:
    return "decoy.cli." + rel.removesuffix(".py").replace("/", ".")


def _forwarder_param(rel: str, func: str) -> str | None:
    entry = FORWARDERS.get(f"{_module(rel)}.{func}")
    return entry[0] if entry else None


def _sites(tree: ast.AST) -> list[tuple[int, ast.expr]]:
    """Every expression that becomes an envelope ``command``, with its line."""
    sites: list[tuple[int, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            sites += [
                (node.lineno, v) for k, v in zip(node.keys, node.values) if _is_command_key(k)
            ]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Subscript) and _is_command_key(t.slice) for t in targets):
                sites.append((node.lineno, node.value))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in {"dict", "update"}:
                sites += [(node.lineno, k.value) for k in node.keywords if k.arg == "command"]
            elif name == "setdefault" and len(node.args) == 2 and _is_command_key(node.args[0]):
                sites.append((node.lineno, node.args[1]))
    return sites


def scan_source(
    source: str, rel: str
) -> tuple[list[tuple[str, int, str]], list[str], dict[str, int]]:
    """One file: (literal values to validate, non-value problems, forwarder call counts)."""
    tree = ast.parse(source)
    values: list[tuple[str, int, str]] = []
    problems: list[str] = []
    spans = [
        (n.lineno, n.end_lineno or n.lineno, n.name)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for line, value in _sites(tree):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append((rel, line, value.value))
            continue
        encl = [sp for sp in spans if sp[0] <= line <= sp[1]]
        func = min(encl, key=lambda sp: sp[1] - sp[0])[2] if encl else None
        param = _forwarder_param(rel, func) if func else None
        if param and isinstance(value, ast.Name) and value.id == param:
            continue
        problems.append(f"{rel}:{line}: envelope command is not a string literal")
    counts: dict[str, int] = {}
    for site in sites(tree):
        call = site.node
        if not isinstance(call, ast.Call):
            continue
        target = site.name
        if target is None and isinstance(call.func, ast.Name):  # a bare same-file call
            target = f"{_module(rel)}.{call.func.id}"
        if target not in FORWARDERS:
            continue
        counts[target] = counts.get(target, 0) + 1
        param, idx, _n = FORWARDERS[target]
        arg = next((k.value for k in call.keywords if k.arg == param), None)
        if arg is None and len(call.args) > idx:
            arg = call.args[idx]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            values.append((rel, call.lineno, arg.value))
        else:
            problems.append(f"{rel}:{call.lineno}: forwarder {target} gets a non-literal")
    return values, problems, counts


def collect() -> tuple[list[tuple[str, int, str]], list[str], dict[str, int]]:
    values: list[tuple[str, int, str]] = []
    problems: list[str] = []
    counts: dict[str, int] = {}
    for path in sorted(CLI_DIR.rglob("*.py")):
        v, p, c = scan_source(
            path.read_text(encoding="utf-8"), path.relative_to(CLI_DIR).as_posix()
        )
        values += v
        problems += p
        for name, n in c.items():
            counts[name] = counts.get(name, 0) + n
    return values, problems, counts


def test_envelope_command_values_are_typeable() -> None:
    paths = visible_paths()
    values, problems, _ = collect()
    bad = [f"{r}:{n}: {v!r}" for r, n, v in values if not is_valid(v, paths)]
    assert bad == [], f"envelope command is not a visible command path: {bad}"
    assert problems == [], f"envelope command the sentry cannot check: {problems}"


def test_forwarder_call_sites_are_pinned() -> None:
    _, _, counts = collect()
    expected = {target: n for target, (_p, _i, n) in FORWARDERS.items()}
    assert counts == expected, "a forwarder gained or lost a call site: update FORWARDERS"


def test_collector_sees_the_known_sites() -> None:
    values, _, _ = collect()
    seen = {v for _, _, v in values}
    assert {"validate", "report fidelity", "report render", "init", "run"} <= seen


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("validate compile", True),
        ("decoy validate preflight", True),
        ("list templates", True),
        ("show schema", True),
        ("compile explain", False),
        ("preflight", False),
        ("scan templates", False),
        ("templates", False),
        ("scan _scan", False),
        ("validate _gate", False),
        ("validate compile extra", False),
    ],
)
def test_validator_bites(value: str, ok: bool) -> None:
    assert is_valid(value, visible_paths()) is ok


SEEDS = {
    "dict literal": 'x = {"command": "bogus cmd"}',
    "dict()": 'x = dict(command="bogus cmd")',
    "update()": 'x.update(command="bogus cmd")',
    "setdefault": 'x.setdefault("command", "bogus cmd")',
    "subscript": 'x["command"] = "bogus cmd"',
    "annotated subscript": 'x["command"]: str = "bogus cmd"',
    "from-import forwarder call": (
        "from decoy.cli.scan import _emit_load_error\n_emit_load_error(s, p, e, 'bogus cmd')"
    ),
    "aliased import": ("from decoy.cli.report import _load_manifest as lm\nlm(p, s, 'bogus cmd')"),
    "module-alias attribute call": (
        "import decoy.cli.report as r\nr._load_manifest(p, s, 'bogus cmd')"
    ),
    "from-import module attribute call": (
        "from decoy.cli import report\nreport._load_manifest(p, s, command='bogus cmd')"
    ),
}


@pytest.mark.parametrize("shape", sorted(SEEDS))
def test_each_shape_is_collected_and_rejected(shape: str) -> None:
    values, _, _ = scan_source(SEEDS[shape], "other.py")
    assert [v for _, _, v in values] == ["bogus cmd"]
    assert not is_valid("bogus cmd", visible_paths())


@pytest.mark.parametrize(
    "source",
    [
        'x = {"command": name}',
        'x["command"] = name',
        "from decoy.cli.scan import _emit_load_error as e2\ne2(s, p, e, name)",
    ],
)
def test_non_literal_is_a_problem(source: str) -> None:
    _, problems, _ = scan_source(source, "other.py")
    assert len(problems) == 1


def test_bare_same_file_forwarder_call_is_collected() -> None:
    values, _, counts = scan_source("_load_manifest(p, s, 'bogus cmd')", "report.py")
    assert [v for _, _, v in values] == ["bogus cmd"]
    assert counts == {"decoy.cli.report._load_manifest": 1}
