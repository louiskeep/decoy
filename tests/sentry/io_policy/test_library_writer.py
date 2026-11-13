"""G-LIB-WRITER: only `decoy.cli.library` writes the record library (plan 3, choke points).

Three rules over every module under `src/decoy/`:

- W1: outside `cli/library/`, no import of a private library module (`decoy.cli.library._fs`,
  `_store`, ...), in any of `import a.b._x`, `from a.b._x import y` or `from a.b import _x`.
  Commands use the facade (`from decoy.cli.library import open_library`).
- W2: outside `cli/library/`, no call to `decoy_engine.records.encode`, the bytes producer, through
  `from decoy_engine.records import encode [as e]`, `from decoy_engine import records [as r]`,
  `import decoy_engine.records [as r]` or the full `decoy_engine.records.encode` chain.
- W3: no string constant outside a docstring (f-string pieces included) with `.decoy` as a path
  component (split on `/` and `\\`), anywhere, the library package included: the folder name
  comes from `decoy.cli.io.DECOY_DIR`. Allowlisted files hold an exact count. `.decoy-ci.yaml`
  and the `.<name>.decoy-<hex>.tmp` staging names are not components equal to `.decoy`.
- W4: outside `cli/library/` and `cli/io/_project.py` (which defines the name and writes only
  `.decoy/.gitignore`), no use of `DECOY_DIR`, by any import form. W2 and W3 alone let a module
  build `find_project(...).root / DECOY_DIR / "library"` and write `records.canonical_bytes`
  through `write_atomic`; the rule anchors on the destination, because `canonical_bytes` has a
  legitimate use outside the library (the evidence manifest hash).

LITERAL_ALLOWLIST starts with two entries (re-FRAME placement map): the managed runtime home
(`distribution/layout.py`) and the project folder name (`cli/io/_project.py`). Shrink-only
ratchet: tests/sentry/baselines/library-writer-allow.json.

Named limits: a name bound at run time (`importlib.import_module`, `getattr(records, "encode")`),
an alias by assignment (`d = DECOY_DIR` is seen once, at the assignment), `from x import *`, and a path built from pieces that are each not
`.decoy` (`"." + "decoy"`) are not seen.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "library-writer-allow.json"
PACKAGE = "cli/library/"
LIBRARY_MODULE = "decoy.cli.library"
RECORDS_MODULE = "decoy_engine.records"
_SPLIT = re.compile(r"[/\\]")


@dataclass(frozen=True)
class AllowedLiteral:
    file: str  # relative to src/decoy
    sites: int
    reason: str


LITERAL_ALLOWLIST: tuple[AllowedLiteral, ...] = (
    AllowedLiteral(
        "distribution/layout.py",
        1,
        "The managed runtime home ~/.decoy (versions, current, cache); swapped on upgrade and "
        "never a record library (plan 4.1).",
    ),
    AllowedLiteral(
        "cli/io/_project.py",
        1,
        "DECOY_DIR, the one home of the project folder name; the library imports it from "
        "decoy.cli.io (re-FRAME placement map).",
    ),
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _private_library_import(node: ast.AST) -> bool:
    def private(dotted: str) -> bool:
        if not dotted.startswith(LIBRARY_MODULE + "."):
            return False
        return dotted[len(LIBRARY_MODULE) + 1 :].split(".")[0].startswith("_")

    if isinstance(node, ast.Import):
        return any(private(a.name) for a in node.names)
    if isinstance(node, ast.ImportFrom) and node.module:
        if private(node.module):
            return True
        return node.module == LIBRARY_MODULE and any(a.name.startswith("_") for a in node.names)
    return False


def _dotted(expr: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    return ".".join([expr.id, *reversed(parts)])


def _encode_calls(tree: ast.AST) -> list[int]:
    """Lines of `decoy_engine.records.encode` calls, resolved through the import forms."""
    modules: dict[str, str] = {}  # local name -> dotted module it stands for
    encoders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    modules[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    modules[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                local = a.asname or a.name
                if node.module == RECORDS_MODULE and a.name == "encode":
                    encoders.add(local)
                else:
                    modules[local] = f"{node.module}.{a.name}"
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in encoders:
            found.append(node.lineno)
            continue
        dotted = _dotted(func)
        if dotted is None or "." not in dotted:
            continue
        head, rest = dotted.split(".", 1)
        if head in modules and f"{modules[head]}.{rest}" == f"{RECORDS_MODULE}.encode":
            found.append(node.lineno)
    return found


_FOLDER_NAME = "DECOY_DIR"
_FOLDER_MODULES = frozenset({"decoy.cli.io", "decoy.cli.io._project"})
_FOLDER_OWNER = "cli/io/_project.py"  # defines the name and writes `.decoy/.gitignore` only


def _folder_name_uses(tree: ast.AST) -> list[int]:
    """Lines that load the project folder name `DECOY_DIR` from `decoy.cli.io`, by any import form.

    The name is how a path into `.decoy/` is built without a literal, so outside the library
    package and the module that defines it, any use of it is a second way into the library.
    """
    names: set[str] = set()
    modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                local = a.asname or a.name
                if node.module in _FOLDER_MODULES and a.name == _FOLDER_NAME:
                    names.add(local)
                else:
                    modules[local] = f"{node.module}.{a.name}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    modules[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    modules[top] = top
    found: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in names:
            found.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == _FOLDER_NAME:
            dotted = _dotted(node.value)
            if dotted is None:
                continue
            head, _, rest = dotted.partition(".")
            if head in modules:
                full = f"{modules[head]}.{rest}" if rest else modules[head]
                if full in _FOLDER_MODULES:
                    found.append(node.lineno)
    return sorted(found)


def _decoy_literals(tree: ast.AST) -> list[int]:
    skip = _docstring_ids(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and ".decoy" in _SPLIT.split(node.value)
    ]


def scan_source(rel: str, source: str) -> list[str]:
    """W1 and W2 findings for one module, plus its W3 lines as `W3:<line>` markers."""
    tree = ast.parse(source)
    inside = rel.startswith(PACKAGE)
    out: list[str] = []
    if not inside:
        out += [
            f"W1: {rel}:{node.lineno} imports a private library module; use the facade"
            for node in ast.walk(tree)
            if _private_library_import(node)
        ]
        out += [
            f"W2: {rel}:{line} calls records.encode; only the library store writes record bytes"
            for line in _encode_calls(tree)
        ]
        if rel != _FOLDER_OWNER:
            out += [
                f"W4: {rel}:{line} builds a path from DECOY_DIR; only the library writes there"
                for line in _folder_name_uses(tree)
            ]
    out += [f"W3:{line}" for line in _decoy_literals(tree)]
    return out


def findings(
    files: dict[str, str], allow: tuple[AllowedLiteral, ...] = LITERAL_ALLOWLIST
) -> list[str]:
    allowed = {e.file: e.sites for e in allow}
    out: list[str] = []
    literal_files: set[str] = set()
    for rel in sorted(files):
        raw = scan_source(rel, files[rel])
        out += [f for f in raw if not f.startswith("W3:")]
        lines = [f.removeprefix("W3:") for f in raw if f.startswith("W3:")]
        if not lines:
            continue
        literal_files.add(rel)
        where = ", ".join(lines)
        if rel not in allowed:
            out.append(f"W3: {rel}: `.decoy` path literal at line(s) {where}; use DECOY_DIR")
        elif len(lines) != allowed[rel]:
            out.append(f"W3: {rel}: {len(lines)} literal(s), allowlist records {allowed[rel]}")
    out += [
        f"W3: {rel}: allowlisted but has no `.decoy` literal (remove the entry)"
        for rel in sorted(set(allowed) - literal_files)
    ]
    return out


def live_files() -> dict[str, str]:
    return {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(SRC.rglob("*.py"))
    }


def test_only_the_library_writes_the_library() -> None:
    assert findings(live_files()) == []


def test_the_library_package_exists_and_is_scanned() -> None:
    files = live_files()
    inside = [rel for rel in files if rel.startswith(PACKAGE)]
    assert {"cli/library/_store.py", "cli/library/_fs.py"} <= set(inside)
    assert any(_encode_calls(ast.parse(files[rel])) for rel in inside)  # the one producer


def test_allowlist_is_two_with_reasons() -> None:
    assert [e.file for e in LITERAL_ALLOWLIST] == ["distribution/layout.py", "cli/io/_project.py"]
    assert all(len(e.reason.strip()) >= 15 and e.sites > 0 for e in LITERAL_ALLOWLIST)


def test_baseline_json_records_the_same_sites_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert {k: (v["sites"], v["reason"]) for k, v in entries.items()} == {
        e.file: (e.sites, e.reason) for e in LITERAL_ALLOWLIST
    }


# -- seeded bypasses: each must go red ---------------------------------------------------------


def test_seeded_inline_library_path_in_scan_is_red() -> None:
    """M-LIB-INLINE: `scan.py` writing `Path(".decoy/library/x.json")` directly."""
    files = live_files()
    seeded = files["cli/scan.py"] + (
        "\n\ndef _inline(data):\n    Path('.decoy/library/x.json').write_bytes(data)\n"
    )
    found = findings({**files, "cli/scan.py": seeded})
    assert len(found) == 1 and found[0].startswith("W3: cli/scan.py: `.decoy` path literal")


@pytest.mark.parametrize(
    "source",
    [
        "import decoy.cli.library._fs\n",
        "from decoy.cli.library._fs import write_once\n",
        "from decoy.cli.library import _store\n",
        "from decoy.cli.library._store import Library\n",
    ],
)
def test_seeded_private_library_import_is_red(source: str) -> None:
    found = findings({"cli/scan.py": source}, ())
    assert len(found) == 1 and found[0].startswith("W1: cli/scan.py:1")


def test_the_facade_import_is_green() -> None:
    assert findings({"cli/scan.py": "from decoy.cli.library import open_library\n"}, ()) == []


@pytest.mark.parametrize(
    "source",
    [
        "from decoy_engine.records import encode\nencode(e)\n",
        "from decoy_engine.records import encode as enc\nenc(e)\n",
        "from decoy_engine import records\nrecords.encode(e)\n",
        "from decoy_engine import records as r\nr.encode(e)\n",
        "import decoy_engine.records as r\nr.encode(e)\n",
        "import decoy_engine.records\ndecoy_engine.records.encode(e)\n",
    ],
)
def test_seeded_records_encode_outside_the_library_is_red(source: str) -> None:
    found = findings({"cli/run/_records.py": source}, ())
    assert len(found) == 1 and found[0].startswith("W2: cli/run/_records.py:2")
    assert findings({"cli/library/_store.py": source}, ()) == []


@pytest.mark.parametrize(
    ("literal", "hit"),
    [
        ('".decoy"', True),
        ('".decoy/library"', True),
        ('"x\\\\.decoy\\\\library"', True),
        ('f"{root}/.decoy/logs"', True),
        ('".decoy-ci.yaml"', False),
        ('".x.decoy-1a2b.tmp"', False),
        ('"persisted to .decoy/workspace.json"', False),
    ],
)
def test_the_component_rule(literal: str, hit: bool) -> None:
    found = findings({"cli/new.py": f"X = {literal}\n"}, ())
    assert bool(found) is hit


def test_a_docstring_mention_is_green_and_a_library_literal_is_red() -> None:
    assert findings({"cli/new.py": '"""Writes under .decoy/library."""\n'}, ()) == []
    found = findings({"cli/library/_paths.py": 'NAME = ".decoy"\n'}, ())
    assert found == ["W3: cli/library/_paths.py: `.decoy` path literal at line(s) 1; use DECOY_DIR"]


def test_stale_and_raised_literal_counts_are_red() -> None:
    files = live_files()
    gone = {k: v for k, v in files.items() if k != "distribution/layout.py"}
    assert any("allowlisted but has no" in f for f in findings(gone))
    doubled = files["cli/io/_project.py"] + '\nOTHER = ".decoy"\n'
    assert any("2 literal(s)" in f for f in findings({**files, "cli/io/_project.py": doubled}))


# -- W4: the folder name used to build a path outside the library (review round 1 on #205) ----

_STRUCTURAL_BYPASS = """
from decoy._atomic import WriteMode, write_atomic
from decoy.cli.io import DECOY_DIR, find_project
from decoy_engine import records


def _inline(config, envelope):
    library = find_project(config.parent, None).root / DECOY_DIR / "library"
    data = records.canonical_bytes(envelope.model_dump())
    write_atomic(library / "objects", "x.json", data, WriteMode.CREATE_ONCE)
"""


def test_seeded_structural_library_write_outside_the_library_is_red() -> None:
    """No literal and no `records.encode`: the root, the folder name and the canonical bytes."""
    files = live_files()
    seeded = files["cli/scan.py"] + "\n" + _STRUCTURAL_BYPASS
    found = findings({**files, "cli/scan.py": seeded})
    assert len(found) == 1 and found[0].startswith("W4: cli/scan.py:"), found


@pytest.mark.parametrize(
    "source",
    [
        "from decoy.cli.io import DECOY_DIR\nP = root / DECOY_DIR\n",
        "from decoy.cli.io import DECOY_DIR as D\nP = root / D\n",
        "from decoy.cli.io._project import DECOY_DIR\nP = root / DECOY_DIR\n",
        "from decoy.cli import io\nP = root / io.DECOY_DIR\n",
        "import decoy.cli.io as cio\nP = root / cio.DECOY_DIR\n",
        "import decoy.cli.io\nP = root / decoy.cli.io.DECOY_DIR\n",
    ],
)
def test_each_spelling_of_the_folder_name_is_seen(source: str) -> None:
    found = findings({"cli/run/_records.py": source}, ())
    assert len(found) == 1 and found[0].startswith("W4: cli/run/_records.py:2"), found
    assert findings({"cli/library/_paths.py": source}, ()) == []


def test_the_folder_name_is_used_only_where_it_is_allowed_today() -> None:
    files = live_files()
    users = sorted(rel for rel in files if _folder_name_uses(ast.parse(files[rel])))
    assert "cli/library/_paths.py" in users or any(u.startswith(PACKAGE) for u in users)
    assert all(u.startswith(PACKAGE) or u == "cli/io/_project.py" for u in users), users
