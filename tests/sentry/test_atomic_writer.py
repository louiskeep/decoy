"""G-ONE-ATOMIC-WRITER: atomic file moves go through `decoy._atomic`.

Walks the syntax tree of every module under `src/decoy/` for the calls that make up an
inline atomic write: `os.replace`, `os.rename`, `os.renames`, `os.link`,
`tempfile.mkstemp` and `shutil.move` (resolved through import aliases and
`from x import y`), plus `.rename(x)` and one-argument `.replace(x)` method calls
(`Path.rename` / `Path.replace`; `str.replace` always takes two arguments). A site
outside `_atomic.py` fails unless its file is in ALLOWLIST with the exact recorded
site count, so a new copy inside an allowlisted file is also red.

Named limits: a call through a name bound at runtime (`getattr(os, "replace")`) is
invisible to a syntax walk; `Path.hardlink_to` is not scanned (no use in the tree).
Size 7 is today's baseline (L1b.1). Entries leave this list when their file moves onto
`_atomic.write_atomic`; none may be added without a reviewed change (shrink-only
ratchet, tests/sentry/baselines/atomic-writer-allow.json).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "_atomic.py"

_MODULE_CALLS = {
    "os": {"replace", "rename", "renames", "link"},
    "tempfile": {"mkstemp"},
    "shutil": {"move"},
}


@dataclass(frozen=True)
class AllowedInline:
    file: str  # relative to src/decoy
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedInline, ...] = (
    AllowedInline(
        "cli/ci.py",
        2,
        "decoy ci output writer; own temp-file recipe, moves onto write_atomic when next touched.",
    ),
    AllowedInline(
        "ci/debug.py",
        2,
        "decoy ci debug log flush; own temp-file recipe, moves onto write_atomic when next touched.",
    ),
    AllowedInline(
        "cli/run.py",
        4,
        "_commit_vault keeps a hard-link backup and restores or removes the vault when the "
        "directory fsync fails (tests/e2e/test_vault_commit_order.py); a transaction, not a "
        "plain atomic write. L5a moves it to _vault_commit.py and renames this entry.",
    ),
    AllowedInline(
        "api.py",
        1,
        "Spools a DataFrame to a throwaway parquet temp file for the engine to read; "
        "never replaced onto a target, so the atomic-write rules do not apply.",
    ),
    AllowedInline(
        "distribution/installer.py",
        4,
        "Swaps whole runtime directories and the launcher shim under the install lock; "
        "a different operation from writing one file.",
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
                if a.name in _MODULE_CALLS:
                    modules[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module in _MODULE_CALLS:
            for a in node.names:
                members[a.asname or a.name] = (node.module, a.name)
    return modules, members


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
            one_arg = len(node.args) == 1 and not node.keywords
            if func.attr == "rename" or (func.attr == "replace" and one_arg):
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


def test_allowlist_baseline_is_seven_with_reasons() -> None:
    assert len(ALLOWLIST) == 7
    assert len({e.file for e in ALLOWLIST}) == 7
    assert all(len(e.reason.strip()) >= 15 and e.sites > 0 for e in ALLOWLIST)


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
    seeded = {**real, "cli/ci.py": [*real["cli/ci.py"], (999, "os.replace")]}
    assert findings(seeded) == ["cli/ci.py: 3 site(s), allowlist records 2 (111, 115, 999)"]


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
