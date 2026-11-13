"""G-ONE-SCAN-READER: `_scan_set.load_scan_set` is the only reader of a saved scan.

Walks the syntax tree of every module under `src/decoy`. Outside `_scan_set.py` no code may
read a `scan_schema` key (subscript, `.get`, `in`, or a comparison against it) or call
`records.decode`, which is how a `scan-set` record envelope would be opened. Writing the key
into a dict literal (the `--json` envelope) is not a read.

One exact-file exemption, for `records.decode` only (owner decision 2026-11-11, LIB L1b.2):
`cli/library/_store.py`, the record library's one reader (`Library.get`). It returns the engine's
typed record for every kind and verifies the id rule; it never reads a `scan_schema` key, which
stays an offender there too. Any other library module or file that decodes is still red.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "decoy"
_READER = "cli/io/_scan_set.py"
_KEY = "scan_schema"
# The one other file that may call `records.decode` (the library's `Library.get`); exact path.
_LIBRARY_STORE = "cli/library/_store.py"


def _is_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == _KEY


def offenders(source: str, *, may_decode: bool = False) -> list[int]:
    """Line numbers where `source` reads the schema key or (unless `may_decode`) decodes a record."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Load)
            and _is_key(node.slice)
        ):
            hits.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr in {"get", "pop", "setdefault"}
                and node.args
                and _is_key(node.args[0])
            ):
                hits.append(node.lineno)
            if (
                not may_decode
                and node.func.attr == "decode"
                and isinstance(node.func.value, ast.Name)
            ):
                if node.func.value.id == "records":
                    hits.append(node.lineno)
        elif isinstance(node, ast.Compare) and any(
            isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
        ):
            if _is_key(node.left):
                hits.append(node.lineno)
    return hits


def test_only_the_reader_reads_a_scan_schema() -> None:
    bad = {}
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        if rel == _READER:
            continue
        found = offenders(path.read_text(encoding="utf-8"), may_decode=rel == _LIBRARY_STORE)
        if found:
            bad[rel] = found
    assert not bad, f"read a saved scan outside load_scan_set: {bad}"


def test_the_library_store_exemption_is_live_and_exact() -> None:
    store = (_SRC / _LIBRARY_STORE).read_text(encoding="utf-8")
    assert offenders(store)  # non-vacuous: the store does decode, so the exemption is in use
    assert offenders(store, may_decode=True) == []
    decode = "def f(blob):\n    return records.decode(blob)\n"
    key = 'def f(data):\n    return data["scan_schema"]\n'
    assert offenders(decode) == [2]  # any file but the store
    assert offenders(key, may_decode=True) == [2]  # the store may not read the key


def test_a_decode_in_another_library_module_is_red(tmp_path: Path) -> None:
    for rel in ("cli/library/_refs.py", "cli/library/_store_copy.py", "cli/scan.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def f(blob):\n    return records.decode(blob)\n", encoding="utf-8")
    bad = {
        p.relative_to(tmp_path).as_posix(): offenders(
            p.read_text(encoding="utf-8"),
            may_decode=p.relative_to(tmp_path).as_posix() == _LIBRARY_STORE,
        )
        for p in sorted(tmp_path.rglob("*.py"))
    }
    assert bad == {
        "cli/library/_refs.py": [2],
        "cli/library/_store_copy.py": [2],
        "cli/scan.py": [2],
    }


def test_the_reader_itself_is_seen_reading_the_key() -> None:
    # Negative control: the walk finds the read it is meant to confine.
    assert offenders((_SRC / _READER).read_text(encoding="utf-8"))


def test_a_seeded_bypass_is_flagged() -> None:
    # M-READ-INLINE: `--compare` checking the tag itself.
    assert offenders('def f(data):\n    return data["scan_schema"]\n')
    assert offenders('def f(data):\n    return data.get("scan_schema")\n')
    assert offenders('def f(data):\n    return "scan_schema" in data\n')
    assert offenders("def f(blob):\n    return records.decode(blob)\n")
    assert not offenders('def f():\n    return {"scan_schema": "scan-set/v1"}\n')


_PRIVATE_SURFACES = {
    "decoy.cli.io._scan_set": "cli/io",
    "decoy.cli.scanning._multi": "cli/scanning",
}


def test_scan_packages_are_used_through_their_public_names() -> None:
    """Outside its own package no module imports `cli.io._scan_set` or `cli.scanning._multi`;
    the owning `__init__` exports the names to use."""
    bad: dict[str, list[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                base = node.module or ""
                names = [base, *(f"{base}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                owner = _PRIVATE_SURFACES.get(name)
                if owner and not rel.startswith(owner + "/"):
                    bad.setdefault(rel, []).append(name)
    assert not bad, f"import the package's public names, not its private module: {bad}"
