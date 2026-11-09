"""G-ONE-ATOMIC-WRITER: atomic file moves go through `decoy._atomic`.

Walks the syntax tree of every module under `src/decoy/` for the calls that make up an
inline atomic write: `os.replace`, `os.rename`, `os.renames`, `os.link`,
`tempfile.mkstemp` and `shutil.move` (resolved through `import x`, `import x.y`,
`import x as y` and `from x import y`), `Path.hardlink_to` / `Path.link_to`, `.rename(...)`,
`.replace(x)` with exactly one argument, or the keyword `target=` (`str.replace` takes two), and the unbound
`Path.replace(a, b)` / `Path.rename(a, b)` (also through `pathlib.Path` and aliases). A site
outside `_atomic.py` fails unless its file is in ALLOWLIST with the exact recorded site count,
so a new copy inside an allowlisted file is also red.

Named limits, all invisible to a syntax walk: a call through a runtime-bound name
(`getattr(os, "replace")`), alias by assignment (`mv = os.replace; mv(a, b)`), a starred
argument list on `.replace(*args)`, and `from os import *`.
Size 4 is today's baseline. L1b.1 left 5 entries, after `cli/ci.py` and `ci/debug.py` moved
onto `_atomic.write_atomic`; X7c S2 then moved `api.py` onto `_private_file`. Entries leave this list when their file moves onto the writer;
none may be added without a reviewed change (shrink-only ratchet,
tests/sentry/baselines/atomic-writer-allow.json, which also records each entry's site count).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "_atomic.py"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "atomic-writer-allow.json"

_MODULE_CALLS: dict[str, set[str]] = {
    "os": {"replace", "rename", "renames", "link"},
    "tempfile": {"mkstemp"},
    "shutil": {"move"},
    "pathlib": set(),  # tracked only to resolve the Path class
}
_PATH_CLASSES = {"Path", "PosixPath", "WindowsPath"}
_PATH_ALWAYS = {"rename", "hardlink_to", "link_to"}


@dataclass(frozen=True)
class AllowedInline:
    file: str  # relative to src/decoy
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedInline, ...] = (
    AllowedInline(
        "cli/run.py",
        4,
        "_commit_vault keeps a hard-link backup and restores or removes the vault when the "
        "directory fsync fails (tests/e2e/test_vault_commit_order.py); a transaction, not a "
        "plain atomic write. L5a moves it to _vault_commit.py and renames this entry.",
    ),
    AllowedInline(
        "distribution/installer.py",
        3,
        "Moves a staged runtime directory into versions/ and writes the 0755 launcher shim "
        "(temp file, chmod, replace); a directory move and an executable-mode write, not a "
        "0600 data write.",
    ),
    AllowedInline(
        "distribution/layout.py",
        1,
        "Flips the current-version symlink under the install lock; not a file write.",
    ),
    AllowedInline(
        "distribution/first_install.py",
        1,
        "Moves the unpacked bundle into place on first install; not a file write.",
    ),
)


def _aliases(tree: ast.AST) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Return ({local name: module}, {local name: (module, attr)}) for the watched modules."""
    modules: dict[str, str] = {}
    members: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if a.asname and a.name in _MODULE_CALLS:
                    modules[a.asname] = a.name
                elif not a.asname and top in _MODULE_CALLS:
                    modules[top] = top  # `import os.path` binds the name `os`
        elif isinstance(node, ast.ImportFrom) and node.module in _MODULE_CALLS:
            for a in node.names:
                members[a.asname or a.name] = (node.module, a.name)
    return modules, members


def _is_path_class(
    node: ast.expr, modules: dict[str, str], members: dict[str, tuple[str, str]]
) -> bool:
    if isinstance(node, ast.Name):
        return members.get(node.id, ("", ""))[0] == "pathlib" and (
            members[node.id][1] in _PATH_CLASSES
        )
    return (
        isinstance(node, ast.Attribute)
        and node.attr in _PATH_CLASSES
        and isinstance(node.value, ast.Name)
        and modules.get(node.value.id) == "pathlib"
    )


def inline_sites(source: str) -> list[tuple[int, str]]:
    """Return (line, what) for each inline atomic-write call in `source`."""
    tree = ast.parse(source)
    modules, members = _aliases(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in members:
            mod, attr = members[func.id]
            if attr in _MODULE_CALLS[mod]:
                found.append((node.lineno, f"{mod}.{attr}"))
        elif isinstance(func, ast.Attribute):
            base = func.value
            if isinstance(base, ast.Name) and modules.get(base.id) in _MODULE_CALLS:
                mod = modules[base.id]
                if func.attr in _MODULE_CALLS[mod]:
                    found.append((node.lineno, f"{mod}.{func.attr}"))
                continue
            keywords = [k.arg for k in node.keywords]
            one_arg = (len(node.args) == 1 and not keywords) or (
                not node.args and keywords == ["target"]
            )
            unbound = func.attr == "replace" and _is_path_class(base, modules, members)
            if func.attr in _PATH_ALWAYS or unbound or (func.attr == "replace" and one_arg):
                found.append((node.lineno, f"Path.{func.attr}"))
    return found


def scan(root: Path) -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if path.name == CHOKE_POINT and path.parent == root:
            continue
        sites = inline_sites(path.read_text(encoding="utf-8"))
        if sites:
            out[rel] = sites
    return out


def findings(found: dict[str, list[tuple[int, str]]]) -> list[str]:
    allowed = {e.file: e.sites for e in ALLOWLIST}
    out = []
    for rel, sites in sorted(found.items()):
        lines = ", ".join(str(n) for n, _ in sites)
        if rel not in allowed:
            out.append(f"{rel}: {len(sites)} inline atomic-write call(s) at line(s) {lines}")
        elif len(sites) != allowed[rel]:
            out.append(f"{rel}: {len(sites)} site(s), allowlist records {allowed[rel]} ({lines})")
    out += [
        f"{rel}: allowlisted but has no inline site (remove the entry)"
        for rel in sorted(set(allowed) - set(found))
    ]
    return out


def test_no_inline_atomic_write_outside_the_choke_point() -> None:
    assert findings(scan(SRC)) == []


def test_allowlist_baseline_is_four_with_reasons() -> None:
    assert len(ALLOWLIST) == 4
    assert len({e.file for e in ALLOWLIST}) == 4
    assert all(len(e.reason.strip()) >= 15 and e.sites > 0 for e in ALLOWLIST)


def test_baseline_json_records_the_same_sites_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert {k: (v["sites"], v["reason"]) for k, v in entries.items()} == {
        e.file: (e.sites, e.reason) for e in ALLOWLIST
    }


def test_choke_point_exists_and_is_excluded() -> None:
    assert (SRC / CHOKE_POINT).is_file()
    assert CHOKE_POINT not in scan(SRC)


def test_seeded_inline_copy_is_red(tmp_path: Path) -> None:
    """M-ATOMIC-INLINE: a new module with its own temp-file replace must be reported."""
    (tmp_path / "_atomic.py").write_text("import os\nos.replace('a', 'b')\n")
    (tmp_path / "newmod.py").write_text(
        "import os, tempfile\nfd, t = tempfile.mkstemp()\nos.replace(t, 'x')\n"
    )
    assert findings(scan(tmp_path)) == [
        "newmod.py: 2 inline atomic-write call(s) at line(s) 2, 3"
    ] + [
        f"{e.file}: allowlisted but has no inline site (remove the entry)"
        for e in sorted(ALLOWLIST, key=lambda e: e.file)
    ]


def test_seeded_copy_in_an_allowlisted_file_is_red() -> None:
    real = {k: v for k, v in scan(SRC).items() if k in {e.file for e in ALLOWLIST}}
    seeded = {**real, "cli/run.py": [*real["cli/run.py"], (999, "os.replace")]}
    lines = ", ".join(str(n) for n, _ in seeded["cli/run.py"])
    recorded = next(e.sites for e in ALLOWLIST if e.file == "cli/run.py")
    assert findings(seeded) == [
        f"cli/run.py: {recorded + 1} site(s), allowlist records {recorded} ({lines})"
    ]


def test_walk_resolves_aliases_and_method_forms() -> None:
    src = (
        "import os as _o\nfrom os import replace as mv\nimport tempfile as t\n"
        "from pathlib import Path\n"
        "_o.link(a, b)\nmv(a, b)\nt.mkstemp()\nPath(a).rename(b)\nPath(a).replace(b)\n"
        "'x'.replace('a', 'b')\nopen(a)\n"
    )
    assert [what for _, what in inline_sites(src)] == [
        "os.link", "os.replace", "tempfile.mkstemp", "Path.rename", "Path.replace",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import os.path\nos.replace(a, b)\n", ["os.replace"]),
        ("import os.path\nos.path.join(a, b)\n", []),
        ("from pathlib import Path\nPath(a).replace(target=b)\n", ["Path.replace"]),
        ("from pathlib import Path\nPath(a).rename(target=b)\n", ["Path.rename"]),
        ("from pathlib import Path\nPath.replace(a, b)\n", ["Path.replace"]),
        ("from pathlib import Path\nPath.rename(a, b)\n", ["Path.rename"]),
        ("from pathlib import Path as P\nP.replace(a, b)\n", ["Path.replace"]),
        ("import pathlib\npathlib.Path.replace(a, b)\n", ["Path.replace"]),
        ("from pathlib import Path\nPath(a).hardlink_to(b)\n", ["Path.hardlink_to"]),
        ("from os import link\nlink(a, b)\n", ["os.link"]),
        ("from os import link as ln\nln(a, b)\n", ["os.link"]),
        ("'x'.replace('a', 'b')\ns.replace(old='a', new='b')\n", []),
        ("import datetime as dt\nd.replace(tzinfo=dt.timezone.utc)\n", []),
        ("from collections import OrderedDict\nOrderedDict.replace(a, b)\n", []),
    ],
)
def test_walk_sees_each_common_form(source: str, expected: list[str]) -> None:
    assert [what for _, what in inline_sites(source)] == expected


def dir_fsync_sites(source: str) -> list[int]:
    """Lines of `os.open(..., O_DIRECTORY)` in a module that also calls `os.fsync`.

    That pair is a hand-written directory fsync; `_atomic.fsync_directory` is the one copy.
    """
    tree = ast.parse(source)
    modules, members = _os_names(tree)
    opens: list[int] = []
    fsyncs = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        what = _os_call(node.func, modules, members)
        if what == "fsync":
            fsyncs += 1
        elif what == "open" and any(
            (isinstance(n, ast.Attribute) and n.attr == "O_DIRECTORY")
            or (isinstance(n, ast.Name) and n.id == "O_DIRECTORY")
            or (isinstance(n, ast.Constant) and n.value == "O_DIRECTORY")
            for arg in [*node.args, *(k.value for k in node.keywords)]
            for n in ast.walk(arg)
        ):
            opens.append(node.lineno)
    return opens if fsyncs else []


def _os_names(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    modules: set[str] = set()
    members: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or "os" for a in node.names if a.name.split(".")[0] == "os"}
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            members |= {a.asname or a.name: a.name for a in node.names}
    return modules, members


def _os_call(func: ast.expr, modules: set[str], members: dict[str, str]) -> str | None:
    if isinstance(func, ast.Name):
        return members.get(func.id)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.attr if func.value.id in modules else None
    return None


def test_no_second_directory_fsync_outside_the_choke_point() -> None:
    found = {
        rel: lines
        for path in sorted(SRC.rglob("*.py"))
        if (rel := path.relative_to(SRC).as_posix()) != CHOKE_POINT
        if (lines := dir_fsync_sites(path.read_text(encoding="utf-8")))
    }
    assert found == {}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import os\nfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY)\nos.fsync(fd)\n", [2]),
        ("import os\nfd = os.open(d, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))\nos.fsync(fd)\n", [2]),
        ("from os import open as op, fsync, O_DIRECTORY\nfd = op(d, O_DIRECTORY)\nfsync(fd)\n", [2]),
        ("import os\nfd = os.open(d, os.O_RDONLY)\nos.fsync(fd)\n", []),
        ("import os\nfd = os.open(d, os.O_DIRECTORY)\n", []),
    ],
)  # fmt: skip
def test_seeded_directory_fsync_is_red(source: str, expected: list[int]) -> None:
    """M-ATOMIC-DIRFSYNC: a hand-written directory fsync is seen; a plain file open is not."""
    assert dir_fsync_sites(source) == expected
