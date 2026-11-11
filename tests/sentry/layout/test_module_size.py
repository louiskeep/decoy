"""Sentry: no CLI module is over 800 lines, and the legacy ones over it only shrink.

The cap covers every ``*.py`` file under ``src/``, ``scripts/`` and ``packaging_tools/``
(``wc -l`` convention, tests not capped). Goal and limit are both 800, so there is no dense
middle band: a file is either at or under 800, or a legacy entry in ``SIZE_ALLOWLIST`` that
must equal its measured count exactly and may only fall. The policy is the engine's shared
``ratchet_verdict`` (vendored ``_layout.py``); the counts were measured on the LAYOUT C2 base.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.sentry.layout import SIZE_TERMS, loc, ratchet_verdict

ROOT = Path(__file__).resolve().parents[3]
LIMIT = 800
TOPS = ("src", "scripts", "packaging_tools")

# Legacy modules over the cap: exact line count at the build base; may only shrink.
SIZE_ALLOWLIST: dict[str, int] = {
    "src/decoy/cli/report.py": 2343,
    "src/decoy/cli/scan.py": 1157,
    "src/decoy/cli/preflight.py": 891,
    "src/decoy/cli/fit.py": 831,
}


def capped_files(root: Path = ROOT) -> list[Path]:
    """Every ``*.py`` file under the capped top-level folders of ``root``."""
    found: list[Path] = []
    for top in TOPS:
        if (root / top).is_dir():
            found += [p for p in (root / top).rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(found)


def rel(path: Path, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def size_reason(path: Path, allowlist: dict[str, int], root: Path = ROOT) -> str | None:
    key = rel(path, root)
    return ratchet_verdict(
        key, loc(path), allowlist.get(key), goal=LIMIT, limit=LIMIT, margin=0, terms=SIZE_TERMS
    )


def census(root: Path, allowlist: dict[str, int]) -> dict[str, str]:
    """The live walk and check over ``root``: file to refusal, failures only."""
    out = {}
    for path in capped_files(root):
        reason = size_reason(path, allowlist, root)
        if reason is not None:
            out[rel(path, root)] = reason
    return out


def test_no_module_over_the_cap_unless_recorded() -> None:
    assert census(ROOT, SIZE_ALLOWLIST) == {}


def test_allowlist_entries_exist_and_are_still_over_the_cap() -> None:
    for key, count in SIZE_ALLOWLIST.items():
        assert (ROOT / key).is_file(), f"SIZE_ALLOWLIST lists a missing file: {key}"
        assert count > LIMIT, f"{key}: recorded at {count}, not over {LIMIT}; delete the entry"


def test_the_walk_reaches_every_capped_folder() -> None:
    tops = {rel(p).split("/", 1)[0] for p in capped_files()}
    assert tops == set(TOPS)


# --- meta-tests: seeded violations prove the guard sees them ------------------------------


LEGACY = "src/decoy/cli/report.py"


def _copy(root: Path, key: str, extra: str = "") -> None:
    dest = root / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text((ROOT / key).read_text(encoding="utf-8") + extra, encoding="utf-8")


def test_a_legacy_module_grown_by_one_line_is_red(tmp_path: Path) -> None:
    _copy(tmp_path, LEGACY, "\n")
    found = census(tmp_path, SIZE_ALLOWLIST)
    assert list(found) == [LEGACY] and "may only shrink" in found[LEGACY]


def test_a_legacy_module_that_shrank_demands_a_ratchet_down(tmp_path: Path) -> None:
    dest = tmp_path / LEGACY
    dest.parent.mkdir(parents=True)
    dest.write_text("x = 1\n" * (SIZE_ALLOWLIST[LEGACY] - 1), encoding="utf-8")
    found = census(tmp_path, SIZE_ALLOWLIST)
    assert list(found) == [LEGACY] and "Ratchet the census down" in found[LEGACY]


def test_a_legacy_module_removed_from_the_allowlist_is_red(tmp_path: Path) -> None:
    key = "src/decoy/cli/scan.py"
    _copy(tmp_path, key)
    rest = {k: v for k, v in SIZE_ALLOWLIST.items() if k != key}
    found = census(tmp_path, rest)
    assert list(found) == [key] and f"over the {LIMIT}-LOC hard max" in found[key]


@pytest.mark.parametrize("top", TOPS)
def test_a_new_module_over_the_cap_in_any_capped_folder_is_red(tmp_path: Path, top: str) -> None:
    planted = tmp_path / top / "deep" / "big.py"
    planted.parent.mkdir(parents=True)
    planted.write_text("x = 1\n" * (LIMIT + 1), encoding="utf-8")
    assert list(census(tmp_path, {})) == [f"{top}/deep/big.py"]


def test_a_module_at_the_cap_passes(tmp_path: Path) -> None:
    planted = tmp_path / "src" / "ok.py"
    planted.parent.mkdir(parents=True)
    planted.write_text("x = 1\n" * LIMIT, encoding="utf-8")
    assert census(tmp_path, {}) == {}
