"""Find the files a `decoy run` placed in its run folder.

A relative target lands at `<project>/out/<name>/<run-id>/<path>`; `LATEST` in the name folder
holds the run id of the last clean run. Tests that check an output read it through here
instead of rebuilding the layout.
"""

from __future__ import annotations

from pathlib import Path


def latest_output(project: Path, rel: str, name: str | None = None) -> Path:
    """`rel` inside the last clean run of pipeline `name` (the only one when `name` is None)."""
    out = project / "out"
    if name is None:
        names = sorted(p.name for p in out.iterdir() if (p / "LATEST").is_file())
        assert len(names) == 1, f"expected one pipeline with a clean run under {out}: {names}"
        name = names[0]
    run_id = (out / name / "LATEST").read_text(encoding="utf-8").strip()
    return out / name / run_id / rel
