"""The launch engine pin is one marked variable, swapped in one place.

Acceptance (B-2): "The engine pin is one marked variable, not hard-coded in
several places." This guards that: the pin's ASSIGNMENT
(`DECOY_LAUNCH_ENGINE_VERSION=...`) exists in exactly one file, `packaging/pin.env`.
Tools and docs may NAME the variable (read it, reference it) freely; what must
not happen is a second file that assigns a launch-engine version, which is how a
D-4 swap would silently miss a copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_FILE = REPO_ROOT / "packaging" / "pin.env"


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def test_pin_env_defines_the_variable():
    text = PIN_FILE.read_text(encoding="utf-8")
    assignments = [
        line for line in text.splitlines() if line.strip().startswith("DECOY_LAUNCH_ENGINE_VERSION=")
    ]
    assert len(assignments) == 1, (
        "packaging/pin.env must assign DECOY_LAUNCH_ENGINE_VERSION exactly once; "
        f"found {len(assignments)}"
    )


def test_no_other_file_assigns_the_launch_engine_pin():
    offenders = []
    for rel in _tracked_files():
        if rel == "packaging/pin.env":
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in text.splitlines():
            stripped = line.strip()
            # A real second assignment. A test string, a doc mention of the NAME,
            # or a shell `source` of pin.env all leave the name without a
            # value-bearing `=` on a non-comment line, so they do not trip.
            if stripped.startswith("DECOY_LAUNCH_ENGINE_VERSION="):
                offenders.append(rel)
    assert not offenders, (
        "DECOY_LAUNCH_ENGINE_VERSION is assigned outside packaging/pin.env: "
        f"{offenders}. The launch engine pin must live in one place (the "
        "orchestrator swaps it there when D-4 lands)."
    )
