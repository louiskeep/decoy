"""AT-F2a: every surface that freezes at 1.0.0 has a row in `docs/release/frozen-surfaces.md`.

The map is the one place that says what is frozen and which test pins it. This sentry reads it with
the CODEMAP path grammar, checks that every test path a row names exists, and enumerates each
completeness source from the code or the source document, so a surface with no row turns it red.
A row may carry `accepted-known-limit: <id>` instead of a test; the readiness instance lists it.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from tests.command_tree import json_leaf_commands
from tests.e2e.release_freeze.write_shapes import SNAPSHOT
from tests.sentry.layout import map_paths, section
from tests.sentry.release import _tags

ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "docs" / "release" / "frozen-surfaces.md"
VERSIONING = ROOT / "docs" / "release" / "versioning.md"
HEADER = ("Surface", "Completeness source", "Owning code", "Pinning test or snapshot")
SURFACE, SOURCE, OWNER, TEST = range(4)
KNOWN_LIMIT = re.compile(r"accepted-known-limit: \S+")


def rows(text: str) -> list[list[str]]:
    lines = [ln for ln in text.splitlines() if ln.startswith("|")]
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines][2:]


def public_surface_items(text: str) -> list[int]:
    """The numbers of the stable items listed under "Public surface" in versioning.md."""
    body = section(text, "## Public surface (the contract MAJOR protects)")
    stable = body.split("These are NOT stable")[0]
    return [int(n) for n in re.findall(r"^(\d+)\. ", stable, flags=re.M)]


def lazy_exports() -> set[str]:
    tree = ast.parse((ROOT / "src" / "decoy" / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_LAZY_API":
            return {
                c.value
                for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    raise AssertionError("src/decoy/__init__.py lost _LAZY_API")


def exit_code_names() -> list[str]:
    tree = ast.parse((ROOT / "src" / "decoy" / "cli" / "exit_codes.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "__all__":
            return [e.value for e in node.value.elts]  # type: ignore[attr-defined]
    raise AssertionError("exit_codes.py lost __all__")


def findings(text: str) -> list[str]:
    """Why ``text`` is not a true frozen-surface map; empty when it is."""
    table = rows(text)
    found = [f"missing path: {m}" for m in map_paths(text, ROOT, (OWNER, TEST))]
    found += [
        f"row without a test: {r[SURFACE]}"
        for r in table
        if "/" not in r[TEST] and not KNOWN_LIMIT.search(r[TEST])
    ]
    sources = " ".join(r[SOURCE] for r in table)
    found += [
        f"no row for versioning.md item {n}"
        for n in public_surface_items(VERSIONING.read_text(encoding="utf-8"))
        if f"item {n}" not in sources
    ]
    exit_row = " ".join(" ".join(r) for r in table if "exit_codes" in r[SOURCE])
    found += [
        f"no row for exit_codes.__all__ name {n}"
        for n in exit_code_names()
        if (n not in exit_row if not n.startswith("EXIT_") else "`EXIT_*`" not in exit_row)
    ]
    api_row = " ".join(" ".join(r) for r in table if "_LAZY_API" in r[SOURCE])
    found += [f"no row for lazy export {n}" for n in sorted(lazy_exports()) if n not in api_row]
    for schema in sorted((ROOT / "docs" / "schemas").glob("*.json")):
        if schema.name not in text:
            found.append(f"no row for docs/schemas/{schema.name}")
    snapshot = SNAPSHOT.relative_to(ROOT).as_posix()
    tagged = _tags.map_tags(text)
    found += [f"no row for tag {tag}" for tag in sorted(_tags.source_tags()) if tag not in tagged]
    needles = ("src/decoy/distribution/", "cli-local-1", "src/decoy/_version.py", snapshot)
    needles += ("S7B-KL-1", "docs/release/public-renames.md")
    needles += ("tests/sentry/release/test_hidden_names.py",)
    for needle in needles:
        if needle not in text:
            found.append(f"no row for {needle}")
    return found


def test_the_map_has_its_four_columns() -> None:
    first = next(ln for ln in MAP.read_text(encoding="utf-8").splitlines() if ln.startswith("|"))
    assert tuple(c.strip() for c in first.strip().strip("|").split("|")) == HEADER


def test_every_row_names_an_existing_test() -> None:
    text = MAP.read_text(encoding="utf-8")
    assert [f for f in findings(text) if f.startswith(("missing path", "row without"))] == []


def test_every_source_item_has_a_row() -> None:
    text = MAP.read_text(encoding="utf-8")
    assert [f for f in findings(text) if f.startswith("no row")] == []


def test_the_evidence_literal_in_the_map_is_the_one_the_writer_emits() -> None:
    writer = (ROOT / "src" / "decoy" / "cli" / "evidence.py").read_text(encoding="utf-8")
    assert '_SCHEMA_VERSION = "cli-local-1"' in writer


def test_the_json_row_is_backed_by_a_snapshot_with_every_json_command() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert set(snapshot) == json_leaf_commands()


def test_the_real_map_is_clean() -> None:
    assert findings(MAP.read_text(encoding="utf-8")) == []


def test_a_dropped_row_is_found() -> None:
    lines = MAP.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines[2:], start=2):
        if line.startswith("|"):
            seeded = "\n".join(lines[:i] + lines[i + 1 :])
            assert findings(seeded) != [], f"dropping row {i} went unnoticed: {line[:60]}"


def test_a_row_pointing_at_a_missing_test_is_found() -> None:
    text = MAP.read_text(encoding="utf-8").replace(
        "tests/unit/test_exit_codes.py", "tests/unit/test_exit_codes_gone.py", 1
    )
    assert any("test_exit_codes_gone.py" in f for f in findings(text))


def test_a_row_with_no_test_cell_is_found() -> None:
    lines = MAP.read_text(encoding="utf-8").splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.startswith("|"))
    cells = lines[first + 2].strip().strip("|").split("|")
    cells[TEST] = " none "
    lines[first + 2] = "|" + "|".join(cells) + "|"
    assert any(f.startswith("row without a test") for f in findings("\n".join(lines)))
