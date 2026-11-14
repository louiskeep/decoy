"""AT-1 (map, C1): every concrete path in the CODEMAP "Where Things Go" section exists.

The section is the one place that says where a new file goes. A path that stops existing, or a
row that is dropped, fails here so the map cannot drift from the tree. Path grammar lives in
``map_paths`` (vendored from the engine's LAYOUT E2 commit ``66d0f879``); the engine's own tests
cover each grammar case, so this file checks the CLI's map and the one CLI-specific wiring.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.sentry.layout import map_paths, section

ROOT = Path(__file__).resolve().parents[3]
# `Goes in`, `File naming`, `Tests`, `Sentries and registries`; column 0 is the kind.
LAYOUT_COLUMNS = (1, 2, 3, 4)
LAYOUT_HEADING = "## Where Things Go"
HEADER = ("Kind", "Goes in", "File naming", "Tests", "Sentries and registries")
# Every kind the map names, so a dropped or renamed row is red with its name. Adding a row means
# adding its kind here in the same reviewed diff.
KINDS = frozenset(
    {
        "Command module",
        "Command-private helpers",
        "Local record library (LIB): root rule, store, and later refs, index, scratch and logs; commands import the facade, never its `_` modules",
        "Generation CLI helpers (the exact fit shared by `fit` and `init`, the `run --rows` preview, the CSV generate scaffold; the flat `cli/` is frozen)",
        "`decoy run` internals (phases, error arm, summary, evidence, notifications, vault commit)",
        "`decoy scan` internals (argument resolution, engine call, card and `--json`)",
        "Pre-run check gate shared by `validate`, `ci check` and `run`",
        "Source readers and target writers (owner rule 2026-11-06: new ones go here from now on)",
        "Project layout services: project root finder and `.decoy/` setup, pipeline names and claims, run folders, `out/`, the Windows path budget, the `layout.*` descriptors. Everything outside `src/decoy/cli/io/` imports them from the public `decoy.cli.io` package",
        "Exit codes",
        "Python API",
        "CI integration",
        "Terminal output",
        "Versioned schema artifacts",
        "User-facing CLI text and crash handling",
        "Shipped install and update",
        "Build-host release tools (not shipped in the wheel)",
        "Packaged templates",
        "Private shared filesystem or process primitives used by more than one package",
        "Notifications, telemetry",
        "First-user QA item tests, grouped by behavior",
        "Sentry test",
        "Layer contracts",
        "Shared cross-suite test helpers (constants and lookups used by more than one test folder)",
        "Developer environment scripts",
        "Release scripts",
        "CI install, vendor and lane policy",
        "Composite CI actions",
        "Task-oriented user guides (one folder per topic, with a `README.md` index)",
        "Root legal files (license text, notice, licensing FAQ, trademark policy)",
        "Roadmap, plans, records",
    }
)
# Paths the map marks `(target)`. A new or misspelled target is red. None is open since C3
# created the layer files.
TARGETS: frozenset[str] = frozenset()
_TARGET = re.compile(r"`([^`]+)` \(target\)")


def _layout_text() -> str:
    return section((ROOT / "CODEMAP.md").read_text(encoding="utf-8"), LAYOUT_HEADING)


def _table() -> list[list[str]]:
    lines = [ln for ln in _layout_text().splitlines() if ln.startswith("|")]
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]


def test_the_codemap_layout_table_has_the_five_named_columns() -> None:
    rows = _table()
    assert tuple(rows[0]) == HEADER
    assert all(len(r) == len(HEADER) for r in rows), "a row has a different number of cells"


def test_the_codemap_layout_section_keeps_its_kinds() -> None:
    kinds = [r[0] for r in _table()[2:]]
    assert len(kinds) == len(set(kinds)), "a kind appears twice"
    assert set(kinds) - KINDS == set(), "a row kind is new or renamed: add it to KINDS"
    assert KINDS - set(kinds) == set(), "the map lost or renamed a row"


def test_the_codemap_target_paths_are_the_approved_ones() -> None:
    found = set(_TARGET.findall(_layout_text()))
    assert found == TARGETS, f"unapproved or missing (target) paths: {found ^ TARGETS}"


def test_every_path_in_the_codemap_layout_section_exists() -> None:
    missing = map_paths(_layout_text(), ROOT, LAYOUT_COLUMNS)
    assert not missing, f"CODEMAP 'Where Things Go' names paths that do not exist: {missing}"


def test_a_missing_concrete_path_in_the_section_is_red() -> None:
    seeded = _layout_text() + "\n| Probe | `src/decoy/nope/` | - | - | - |\n"
    assert map_paths(seeded, ROOT, LAYOUT_COLUMNS) == ["src/decoy/nope/ -> src/decoy/nope"]


def test_a_target_path_with_a_real_parent_is_green() -> None:
    seeded = "| Probe | `src/decoy/cli/newpkg/` (target) | - | - | - |\n"
    assert map_paths(seeded, ROOT, LAYOUT_COLUMNS) == []
