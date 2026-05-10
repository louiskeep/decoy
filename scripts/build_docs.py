#!/usr/bin/env python3
"""Regenerate the auto-generated documentation artifacts.

Outputs (under ``docs/diagrams/``):
  deps.svg              Module dependency graph (pydeps)
  classes_decoy.svg     Class diagram for src/decoy (pyreverse)
  packages_decoy.svg    Package diagram for src/decoy (pyreverse)

Requires: pydeps, pylint, graphviz (the ``dot`` binary).
Install with: pip install pydeps pylint && apt-get install graphviz

Run from the repo root:
    python scripts/build_docs.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src" / "decoy"
OUT_DIR = REPO_ROOT / "docs" / "diagrams"


def require(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"error: required tool {tool!r} not found on PATH")


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main() -> None:
    for tool in ("pydeps", "pyreverse", "dot"):
        require(tool)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    run([
        "pydeps", str(SRC_DIR),
        "--max-bacon", "3",
        "--cluster",
        "--no-show",
        "-T", "svg",
        "-o", str(OUT_DIR / "deps.svg"),
    ])

    run([
        "pyreverse",
        "-o", "svg",
        "-d", str(OUT_DIR),
        "-p", "decoy",
        str(SRC_DIR),
    ])

    print(f"\nDone. Diagrams written to: {OUT_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
