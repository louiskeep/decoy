"""G-ONE-OUTPUT-PLACE: output paths are built by `RunLayout`, not by each command.

Three rules, each over every module under `src/decoy/`:

(a) `resolve_path` (the input-side YAML path resolver, any import spelling) is called only where
    a path is read or compared, listed in ALLOWLIST with the exact site count. `RunLayout` is the
    one writer-side caller. The baseline may shrink and never grow
    (tests/sentry/baselines/output-placement-allow.json, checked by scripts/dev/ratchet_check.py).
(b) Path-building calls (`with_suffix`, `with_name`, `joinpath`, `Path(...)`, a `/` join) that use
    a default side-file name (`.unmasked`, `.detokenized`, `.snapshot.json`, `.masked`) or the
    `out` folder literal sit only in `cli/io/_layout.py` and `cli/project/_scaffold.py`, except
    the sites in NAME_ALLOWLIST that later slices move there (shrink-only baseline
    tests/sentry/baselines/output-name-allow.json).
(c) `write_targets` and `write_chunked_output` take their placement as a `RunLayout`.
(d) `decoy validate`'s target check reaches a target path only through `place_target`.

A syntax walk: a path built through a runtime-bound name, or a literal assembled from pieces, is
not seen.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import call_sites, tally

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "output-placement-allow.json"
NAME_BASELINE = ROOT / "tests" / "sentry" / "baselines" / "output-name-allow.json"
PLACERS = ("cli/io/_layout.py", "cli/project/_scaffold.py")
NAME_LITERALS = (".unmasked", ".detokenized", ".snapshot.json", ".masked")
OUT_LITERAL = "out"
BUILDERS = frozenset({"with_suffix", "with_name", "joinpath", "Path", "PurePath"})
WRITERS = ("write_targets", "write_chunked_output")
TARGETS = "cli/io/_targets.py"
PREFLIGHT = "cli/preflight.py"
TARGET_CHECK = "_check_target_overwrite"


@dataclass(frozen=True)
class AllowedSite:
    file: str  # relative to src/decoy
    function: str
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedSite, ...] = (
    AllowedSite(
        "cli/io/_layout.py",
        "RunLayout.place_target",
        1,
        "The one placement site: a fixed layout and an absolute path resolve as the old code did.",
    ),
    AllowedSite(
        "cli/io/_targets.py",
        "_is_declared_target",
        1,
        "Compares a file with the declared target path; reads, writes nothing.",
    ),
    AllowedSite(
        "cli/run/_execute.py",
        "_run_chunked_mask",
        1,
        "Resolves the chunked source path for the empty-parquet schema; an input.",
    ),
    AllowedSite(
        "cli/run/_prepare.py",
        "prepare",
        1,
        "Resolves the --duckdb-source database path; an input.",
    ),
)

# Default side-file names built in place today. Each moves into `cli/io/_layout.py` in P9 (or
# `cli/project/_scaffold.py` in P7) and leaves this list.
NAME_ALLOWLIST: tuple[AllowedSite, ...] = (
    AllowedSite("cli/fit.py", "fit", 1, "Default snapshot name beside the source; moves in P9."),
    AllowedSite(
        "cli/gen/_scaffold.py",
        "layout_for",
        1,
        "Snapshot name in the generate scaffold; moves with the scaffold in P7.",
    ),
    AllowedSite(
        "cli/tokenize.py",
        "detokenize",
        1,
        "Default detokenized name beside the input; moves in P9.",
    ),
    AllowedSite(
        "cli/unmask.py", "unmask", 1, "Default unmasked name beside the input; moves in P9."
    ),
)


def _resolve_sites(source: str) -> list[tuple[int, str]]:
    return call_sites(source, qualified_match=lambda _module, member: member == "resolve_path")


def _has_literal(node: ast.AST, *, exact_out: bool) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if any(lit in child.value for lit in NAME_LITERALS):
                return True
            if exact_out and child.value == OUT_LITERAL:
                return True
    return False


def _builder_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def name_sites(source: str) -> list[tuple[int, str]]:
    """(line, qualified function) for each path-building node using a watched literal."""
    found: list[tuple[int, str]] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = child.name if scope == "<module>" else f"{scope}.{child.name}"
                visit(child, qual)
                continue
            if isinstance(child, ast.Call) and _builder_name(child) in BUILDERS:
                if any(_has_literal(a, exact_out=False) for a in (*child.args, *child.keywords)):
                    found.append((child.lineno, scope))
            elif isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
                if _has_literal(child.right, exact_out=True):
                    found.append((child.lineno, scope))
            visit(child, scope)

    visit(ast.parse(source), "<module>")
    return found


def _allowed(entries: tuple[AllowedSite, ...]) -> dict[tuple[str, str], int]:
    return {(a.file, a.function): a.sites for a in entries}


def _name_tally(root: Path) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in PLACERS:
            continue
        for _line, scope in name_sites(path.read_text(encoding="utf-8")):
            counts[(rel, scope)] = counts.get((rel, scope), 0) + 1
    return counts


def _resolve_tally(root: Path) -> dict[tuple[str, str], int]:
    return tally(root, skip="", finder=_resolve_sites)


# --- (a) resolve_path --------------------------------------------------------------------


def test_resolve_path_is_called_only_at_listed_sites() -> None:
    found, allowed = _resolve_tally(SRC), _allowed(ALLOWLIST)
    extra = {k: n for k, n in found.items() if allowed.get(k, 0) < n}
    assert not extra, f"resolve_path called outside the listed sites: {sorted(extra)}"


def test_resolve_path_allowlist_is_live_and_exact() -> None:
    found = _resolve_tally(SRC)
    stale = {k: n for k, n in _allowed(ALLOWLIST).items() if found.get(k, 0) != n}
    assert not stale, f"allowlist entries that no longer match the code: {sorted(stale)}"


@pytest.mark.parametrize(
    ("baseline", "allowlist"), [(BASELINE, ALLOWLIST), (NAME_BASELINE, NAME_ALLOWLIST)]
)
def test_baseline_json_records_the_same_entries_and_reasons(
    baseline: Path, allowlist: tuple[AllowedSite, ...]
) -> None:
    entries = json.loads(baseline.read_text(encoding="utf-8"))["entries"]
    expected = {f"{a.file}::{a.function}": {"reason": a.reason} for a in allowlist}
    assert entries == expected


def test_allowlist_has_reasons_and_unique_identities() -> None:
    assert len(_allowed(ALLOWLIST)) == len(ALLOWLIST)
    assert len(_allowed(NAME_ALLOWLIST)) == len(NAME_ALLOWLIST)
    assert all(len(a.reason) >= 15 for a in (*ALLOWLIST, *NAME_ALLOWLIST))


@pytest.mark.parametrize(
    "source",
    [
        "from decoy.cli.io import resolve_path\ndef f(p, b):\n    return resolve_path(p, b)\n",
        "from decoy.cli.io import resolve_path as rp\ndef f(p, b):\n    return rp(p, b)\n",
        "from decoy.cli._sources import resolve_path\ndef f(p, b):\n    return resolve_path(p, b)\n",
        "import decoy.cli.io as io\ndef f(p, b):\n    return io.resolve_path(p, b)\n",
    ],
)
def test_walk_sees_each_spelling_of_resolve_path(source: str) -> None:
    assert [scope for _l, scope in _resolve_sites(source)] == ["f"]


# --- (b) default names and the out folder ------------------------------------------------


def test_default_names_and_out_are_built_only_by_the_placers() -> None:
    found, allowed = _name_tally(SRC), _allowed(NAME_ALLOWLIST)
    extra = {k: n for k, n in found.items() if allowed.get(k, 0) < n}
    assert not extra, f"path built from a layout literal outside the placers: {sorted(extra)}"


def test_name_allowlist_is_live_and_exact() -> None:
    found = _name_tally(SRC)
    stale = {k: n for k, n in _allowed(NAME_ALLOWLIST).items() if found.get(k, 0) != n}
    assert not stale, f"name allowlist entries that no longer match the code: {sorted(stale)}"


@pytest.mark.parametrize(
    "source",
    [
        "def f(p):\n    return p.with_suffix('.unmasked.csv')\n",
        "from pathlib import Path\ndef f(s):\n    return Path(f'{s}.masked.csv')\n",
        "def f(root):\n    return root / 'out' / 'x'\n",
        "def f(p):\n    return p.with_name('a.snapshot.json')\n",
        "def f(p):\n    return p.parent.joinpath('x.detokenized.csv')\n",
    ],
)
def test_walk_sees_each_path_building_spelling(source: str) -> None:
    assert [scope for _l, scope in name_sites(source)] == ["f"]


@pytest.mark.parametrize(
    "source",
    [
        "def f(p):\n    return p.with_suffix('.csv')\n",
        "def f(root):\n    return root / 'output'\n",
        "def f():\n    return 'we mask out the ssn'\n",
    ],
)
def test_walk_ignores_lookalikes(source: str) -> None:
    assert name_sites(source) == []


def test_a_seeded_name_build_in_a_command_is_caught() -> None:
    seeded = "def unmask(p):\n    return p.with_suffix('.unmasked.csv')\n"
    assert name_sites(seeded) == [(2, "unmask")]


# --- (c) the writers take a RunLayout ------------------------------------------------------


def _layout_annotated(source: str, writer: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == writer:
            args = [*node.args.args, *node.args.kwonlyargs]
            return any(
                isinstance(a.annotation, ast.Name) and a.annotation.id == "RunLayout" for a in args
            )
    return False


@pytest.mark.parametrize("writer", WRITERS)
def test_each_writer_annotates_its_placement_parameter_as_run_layout(writer: str) -> None:
    source = (SRC / TARGETS).read_text(encoding="utf-8")
    assert _layout_annotated(source, writer)


def test_a_writer_back_on_a_base_dir_is_caught() -> None:
    seeded = "def write_targets(config_dict, outputs, base_dir: Path):\n    pass\n"
    assert not _layout_annotated(seeded, "write_targets")


# --- (d) validate's target check builds no path of its own ----------------------------------


def _target_check_builds_path(source: str) -> bool | None:
    """True when the target check skips `place_target`, builds a path or asks `os.path.isabs`.

    None when the function is missing, so a rename fails the test instead of passing it.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == TARGET_CHECK:
            names = {_builder_name(c) for c in ast.walk(node) if isinstance(c, ast.Call)}
            return "place_target" not in names or bool(names & (BUILDERS | {"isabs"}))
    return None


def test_validate_target_check_places_targets_only_through_place_target() -> None:
    source = (SRC / PREFLIGHT).read_text(encoding="utf-8")
    assert _target_check_builds_path(source) is False


@pytest.mark.parametrize(
    "body",
    [
        "out = Path(raw)",
        "out = PurePath(raw)",
        "out = layout.place_target(raw)\n    other = Path(raw)",
        "out = layout.place_target(raw) if os.path.isabs(raw) else None",
        "out = raw",
    ],
)
def test_a_direct_path_in_the_target_check_is_caught(body: str) -> None:
    seeded = f"def {TARGET_CHECK}(raw, layout):\n    {body}\n"
    assert _target_check_builds_path(seeded) is True
