"""Engine internal-boundary sentry for the decoy CLI.

`decoy_engine.internal` and any `_private` engine name are not a public surface: the engine
may move or delete them in any release with no compatibility notice. They also resolve today,
so the resolve-only sentry (`test_engine_import_surface.py`) cannot see the drift coming.
This sentry bans them from `src/decoy` outright, except for an explicit allowlist in which
every entry carries a reason and a removal note.

Scope: static references only. It sees imports of any form (`import`, `from ... import`,
aliased or nested), `_private` attribute reads through any binding that came from a
`decoy_engine` import, and string-literal `importlib.import_module(...)` / `__import__(...)`
targets. A dynamically built module name is not resolvable statically and is not seen.
Dunder names (`__version__`) are public by Python convention and are not flagged.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "decoy"
_ENGINE = "decoy_engine"


@dataclass(frozen=True)
class AllowedInternal:
    file: str  # path relative to src/decoy
    ref: str  # dotted engine name exactly as the scan reports it
    reason: str
    removal: str  # what has to land, and where, before this entry can be deleted


# Entries are added only when the pinned engine and engine main have no public equivalent.
ALLOWLIST: tuple[AllowedInternal, ...] = ()


def _is_private(segment: str) -> bool:
    return segment.startswith("_") and not (segment.startswith("__") and segment.endswith("__"))


def _bad_segment(segment: str) -> bool:
    return segment == "internal" or _is_private(segment)


def _first_bad_prefix(dotted: str) -> str | None:
    """`dotted` truncated at its first `internal` / `_private` segment below the
    engine root, else None."""
    parts = dotted.split(".")
    for i, seg in enumerate(parts[1:], start=1):
        if _bad_segment(seg):
            return ".".join(parts[: i + 1])
    return None


def _is_engine(name: str) -> bool:
    return name == _ENGINE or name.startswith(_ENGINE + ".")


def _chain(node: ast.expr) -> list[str] | None:
    """`a.b.c` -> ["a", "b", "c"]; None when the base is not a plain name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def internal_refs(root: Path) -> list[tuple[str, str, str]]:
    """(relative path, dotted ref, "path:line") for every boundary violation."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        alias: dict[str, str] = {}  # local binding -> dotted engine path it names

        def add(ref: str, node: ast.AST, rel: str = rel) -> None:
            if (bad := _first_bad_prefix(ref)) is not None:
                found.append((rel, bad, f"{rel}:{getattr(node, 'lineno', '?')}"))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if not _is_engine(node.module):
                    continue
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    add(full, node)
                    alias[a.asname or a.name] = full
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if not _is_engine(a.name):
                        continue
                    add(a.name, node)
                    alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else _ENGINE
            elif isinstance(node, ast.Call):
                callee = _chain(node.func)
                if callee and callee[-1] in {"import_module", "__import__"} and node.args:
                    arg = node.args[0]
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and _is_engine(arg.value)
                    ):
                        add(arg.value, node)

        if not alias:
            continue
        # Maximal attribute chains only, so `m._p.q` reports once, at `m._p`.
        inner = {
            id(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or id(node) in inner:
                continue
            chain = _chain(node)
            if not chain or chain[0] not in alias:
                continue
            base = alias[chain[0]]
            # The binding's own path was judged at its import; judge only what the
            # attribute accesses add on top of it.
            for i, seg in enumerate(chain[1:], start=1):
                if _bad_segment(seg):
                    found.append(
                        (rel, ".".join([base, *chain[1 : i + 1]]), f"{rel}:{node.lineno}")
                    )
                    break
    return found


def unallowed_internal_refs(
    root: Path, allowlist: tuple[AllowedInternal, ...] = ALLOWLIST
) -> list[str]:
    allowed = {(a.file, a.ref) for a in allowlist}
    return [
        f"{where}: {ref}" for rel, ref, where in internal_refs(root) if (rel, ref) not in allowed
    ]


# --- the sentry ----------------------------------------------------------------


def test_cli_does_not_import_engine_internals() -> None:
    """No `decoy_engine.internal.*` or engine `_private` reference in `src/decoy`
    outside the allowlist."""
    problems = unallowed_internal_refs(_SRC)
    assert not problems, (
        "The CLI reaches into engine internals (not a public surface; the engine may "
        "move them without notice). Use the public export, or if none exists list the "
        "needed symbol in docs/handoffs/inputs/cli-needs-engine-public-api.md and add an "
        "ALLOWLIST entry with a removal note:\n  - " + "\n  - ".join(problems)
    )


def test_every_allowlist_entry_is_justified_and_still_needed() -> None:
    """The allowlist may only shrink: an entry needs a reason and a removal note, and
    must match a reference that still exists (a fixed site must drop its entry)."""
    live = {(rel, ref) for rel, ref, _ in internal_refs(_SRC)}
    for entry in ALLOWLIST:
        assert entry.reason.strip(), entry
        assert entry.removal.strip(), entry
        assert (entry.file, entry.ref) in live, f"stale allowlist entry: {entry}"
    assert len({(a.file, a.ref) for a in ALLOWLIST}) == len(ALLOWLIST), "duplicate entry"


def test_boundary_scan_reaches_nested_packages(tmp_path: Path) -> None:
    """A violation in a deep subpackage is found: a refactor cannot narrow the walk."""
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "mod.py").write_text("import decoy_engine.internal.fs\n", encoding="utf-8")
    assert [rel for rel, _, _ in internal_refs(tmp_path)] == ["a/b/mod.py"]


# --- negative controls: the mechanism must actually bite --------------------------


def _scan(tmp_path: Path, source: str) -> list[str]:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return [ref for _, ref, _ in internal_refs(tmp_path)]


def test_flags_each_import_shape_of_an_internal_module(tmp_path: Path) -> None:
    shapes = {
        "import decoy_engine.internal.logging\n": ["decoy_engine.internal"],
        "import decoy_engine.internal.logging as lg\n": ["decoy_engine.internal"],
        "from decoy_engine.internal.faker_setup import get_faker_providers\n": [
            "decoy_engine.internal"
        ],
        "from decoy_engine.internal import faker_setup\n": ["decoy_engine.internal"],
        "from decoy_engine import internal\n": ["decoy_engine.internal"],
        "def f():\n    from decoy_engine.internal.fs import x\n": ["decoy_engine.internal"],
        "try:\n    import decoy_engine.internal.base\nexcept ImportError:\n    pass\n": [
            "decoy_engine.internal"
        ],
    }
    for source, expected in shapes.items():
        assert _scan(tmp_path, source) == expected, source


def test_flags_private_engine_names(tmp_path: Path) -> None:
    assert _scan(tmp_path, "from decoy_engine import _hidden\n") == ["decoy_engine._hidden"]
    assert _scan(tmp_path, "from decoy_engine.kernel import _impl\n") == [
        "decoy_engine.kernel._impl"
    ]
    assert _scan(tmp_path, "import decoy_engine._core\n") == ["decoy_engine._core"]
    assert _scan(tmp_path, "from decoy_engine._core.x import y\n") == ["decoy_engine._core"]


def test_flags_private_attribute_reads_through_any_engine_binding(tmp_path: Path) -> None:
    assert _scan(tmp_path, "import decoy_engine\nx = decoy_engine._state\n") == [
        "decoy_engine._state"
    ]
    assert _scan(tmp_path, "import decoy_engine\nx = decoy_engine.internal.logging\n") == [
        "decoy_engine.internal"
    ]
    assert _scan(tmp_path, "from decoy_engine import kernel\nkernel._cache.clear()\n") == [
        "decoy_engine.kernel._cache"
    ]
    assert _scan(tmp_path, "import decoy_engine.kernel as k\nk._cache = None\n") == [
        "decoy_engine.kernel._cache"
    ]


def test_flags_literal_dynamic_imports(tmp_path: Path) -> None:
    source = (
        "import importlib\n"
        "m = importlib.import_module('decoy_engine.internal.logging')\n"
        "n = __import__('decoy_engine.internal.base')\n"
    )
    assert _scan(tmp_path, source) == ["decoy_engine.internal", "decoy_engine.internal"]


def test_does_not_flag_public_engine_use_or_unrelated_private_names(tmp_path: Path) -> None:
    source = (
        "import decoy_engine\n"
        "from decoy_engine import run_pipeline, list_generate_faker_providers\n"
        "from decoy_engine.keyprovider import make_key_resolver\n"
        "import decoy_engine.sdk as sdk\n"
        "v = decoy_engine.__version__\n"
        "class C:\n    _own = 1\n"
        "c = C()._own\n"
        "from other_pkg.internal import thing\n"
        "import other_pkg._private\n"
        "import importlib\nimportlib.import_module('other_pkg.internal')\n"
        "sdk.run_config_only_checks\n"
    )
    assert _scan(tmp_path, source) == []


def test_allowlist_excuses_exactly_its_file_and_ref(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import decoy_engine.internal.logging\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("import decoy_engine.internal.logging\n", encoding="utf-8")
    allow = (AllowedInternal("ok.py", "decoy_engine.internal", "r", "x"),)
    left = unallowed_internal_refs(tmp_path, allow)
    assert len(left) == 1 and left[0].startswith("other.py:1"), left
