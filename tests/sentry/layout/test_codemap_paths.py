"""AT-1 (map, C1): every concrete path in the CODEMAP "Where Things Go" section exists.

The section is the one place that says where a new file goes. A path that stops existing, or a
row that is dropped, fails here so the map cannot drift from the tree. Path grammar lives in
``map_paths`` (vendored from the engine's LAYOUT E1 commit ``7a61be3c``); the engine's own tests
cover each grammar case, so this file checks the CLI's map and the one CLI-specific wiring.
"""

from __future__ import annotations

from pathlib import Path

from tests.sentry.layout import map_paths, section

ROOT = Path(__file__).resolve().parents[3]
# `Goes in`, `File naming`, `Tests`, `Sentries and registries`; column 0 is the kind.
LAYOUT_COLUMNS = (1, 2, 3, 4)
LAYOUT_HEADING = "## Where Things Go"
MIN_ROWS = 25


def _layout_text() -> str:
    return section((ROOT / "CODEMAP.md").read_text(encoding="utf-8"), LAYOUT_HEADING)


def test_the_codemap_layout_section_keeps_its_rows() -> None:
    rows = [line for line in _layout_text().splitlines() if line.startswith("| ") and "`" in line]
    assert len(rows) >= MIN_ROWS, "the CODEMAP layout section lost its rows"


def test_every_path_in_the_codemap_layout_section_exists() -> None:
    missing = map_paths(_layout_text(), ROOT, LAYOUT_COLUMNS)
    assert not missing, f"CODEMAP 'Where Things Go' names paths that do not exist: {missing}"


def test_a_missing_concrete_path_in_the_section_is_red() -> None:
    seeded = _layout_text() + "\n| Probe | `src/decoy/nope/` | - | - | - |\n"
    assert map_paths(seeded, ROOT, LAYOUT_COLUMNS) == ["src/decoy/nope/ -> src/decoy/nope"]


def test_a_target_path_with_a_real_parent_is_green() -> None:
    seeded = "| Probe | `src/decoy/cli/newpkg/` (target) | - | - | - |\n"
    assert map_paths(seeded, ROOT, LAYOUT_COLUMNS) == []
