"""G-ONE-SMALL-FILE: one safe small-file reader under `src/decoy/cli/`.

`cli/io/_small_file.py::read_small_file` is the only place under `cli/` that opens a file without
following links. A second copy drifts: an earlier pair differed on what happened when the platform
had no `O_NOFOLLOW`. The scan flags any mention of `O_NOFOLLOW` outside that module: `os.O_NOFOLLOW`
or any `<x>.O_NOFOLLOW`, a bare name brought in by `from os import O_NOFOLLOW`, and the string
`"O_NOFOLLOW"` that `getattr(os, "O_NOFOLLOW", 0)` uses.

Named limits of a syntax walk: a flag built from a number, or a name assembled at run time.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "src" / "decoy" / "cli"
READER = "io/_small_file.py"
_FLAG = "O_NOFOLLOW"


def no_follow_lines(source: str) -> list[int]:
    """Lines that name the no-follow open flag, by attribute, import, name or string."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == _FLAG:
            lines.add(node.lineno)
        elif isinstance(node, ast.Name) and node.id == _FLAG:
            lines.add(node.lineno)
        elif isinstance(node, ast.ImportFrom) and any(a.name == _FLAG for a in node.names):
            lines.add(node.lineno)
        elif isinstance(node, ast.Constant) and node.value == _FLAG:
            lines.add(node.lineno)
    return sorted(lines)


def bypasses(files: dict[str, str]) -> list[str]:
    """`<path>:<line>` for every no-follow flag outside the one reader."""
    return [
        f"{rel}:{line}"
        for rel, source in sorted(files.items())
        if rel != READER
        for line in no_follow_lines(source)
    ]


def _cli_files() -> dict[str, str]:
    return {
        p.relative_to(CLI).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(CLI.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


def test_only_the_small_file_reader_opens_without_following_links() -> None:
    files = _cli_files()
    assert READER in files, f"the reader moved; update READER ({READER})"
    assert no_follow_lines(files[READER]), "the reader no longer names O_NOFOLLOW"
    assert bypasses(files) == []


# --- seeded bypasses: each spelling turns the scan red ------------------------------------


def test_each_spelling_of_the_flag_is_seen() -> None:
    seeds = {
        "a.py": "import os\nflags = os.O_RDONLY | os.O_NOFOLLOW\n",
        "b.py": 'import os\nflags = getattr(os, "O_NOFOLLOW", 0)\n',
        "c.py": "from os import O_NOFOLLOW\n",
        "d.py": "import os as o\nf = o.O_NOFOLLOW\n",
    }
    assert bypasses(seeds) == ["a.py:2", "b.py:2", "c.py:1", "d.py:2"]


def test_the_reader_itself_and_unrelated_code_are_allowed() -> None:
    seeds = {READER: "import os\nf = os.O_NOFOLLOW\n", "e.py": "import os\nf = os.O_RDONLY\n"}
    assert bypasses(seeds) == []
