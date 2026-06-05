"""Source-hygiene sentry for the decoy CLI.

A mechanical guard beyond ruff: the public OSS source must stay ASCII-clean
of em-dashes (U+2014) and arrows (U+2192, U+2194) so it greps, diffs, and
renders the same in every terminal. chr() keeps this file itself glyph-free
so it never trips its own check.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "decoy"
_TESTS = _ROOT / "tests"
_BANNED_GLYPHS = (chr(0x2014), chr(0x2192), chr(0x2194))


def _files_with_banned_glyphs(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(glyph in text for glyph in _BANNED_GLYPHS):
            hits.append(path.relative_to(root).as_posix())
    return hits


def test_no_raw_em_dash_or_arrow_in_source() -> None:
    """src/ and tests/ must be ASCII-clean of em-dashes (U+2014) and
    arrows (U+2192 / U+2194). Use a hyphen, '->', or '<->'. Keeps the
    public OSS source greppable and enforces the no-em-dash rule."""
    offenders = [f"src/decoy/{rel}" for rel in _files_with_banned_glyphs(_SRC)]
    offenders += [f"tests/{rel}" for rel in _files_with_banned_glyphs(_TESTS)]
    assert not offenders, (
        "Raw em-dash / arrow glyphs (U+2014 / U+2192 / U+2194) in:\n  - "
        + "\n  - ".join(offenders)
        + "\nReplace with '-', '->', or '<->'."
    )


def test_banned_glyph_sentry_flags_injected_em_dash(tmp_path: Path) -> None:
    """Negative control: the scan must actually catch a raw em-dash, so a
    future refactor cannot quietly neuter the guard into a no-op."""
    injected = tmp_path / "injected.py"
    injected.write_text("x = 1  " + chr(0x2014) + " note\n", encoding="utf-8")
    assert _files_with_banned_glyphs(tmp_path) == ["injected.py"]
