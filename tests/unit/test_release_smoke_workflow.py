"""Drift guard for the release-smoke CI workflow file (OSS.1 commit 3).

The workflow file at `.github/workflows/release-smoke.yml` is the
launch-day DX gate the README §8 R2 risk depends on. If a future
contributor silently empties the file, drops the Python matrix, or
removes one of the canonical smoke cells, this test trips before the
gate goes quiet.

This is a SHAPE check, not an execution test. The real verification
is the workflow itself running in CI; this only catches "did someone
delete the gate?" between releases.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent.parent
    / ".github"
    / "workflows"
    / "release-smoke.yml"
)


def test_release_smoke_workflow_file_exists() -> None:
    assert WORKFLOW.exists(), (
        f"{WORKFLOW.name} was deleted; the OSS-CLI launch gate is gone. "
        "Recreate the file or call out the removal in a sprint spec."
    )


def test_release_smoke_workflow_pins_three_python_versions() -> None:
    """OSS.1 commits to a Python 3.10 + 3.11 + 3.12 matrix. Adding a
    version requires a deliberate edit to this test."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = data["jobs"]["fresh-install"]
    python_versions = set(job["strategy"]["matrix"]["python"])
    assert python_versions == {"3.10", "3.11", "3.12"}, (
        f"release-smoke Python matrix drifted from {{3.10, 3.11, 3.12}}: "
        f"now {python_versions}. If this is intentional, update both "
        f"the matrix and this assertion in the same commit."
    )


def test_release_smoke_workflow_runs_canonical_smoke_cells() -> None:
    """The three canonical CLI cells (`decoy --version`, `decoy demo
    --json`, the `decoy run` cell against the bundled minimal template)
    must all appear in the workflow's step list. The check is on the
    `run:` text of each step; spelling matters."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["fresh-install"]["steps"]
    run_bodies = "\n".join(s.get("run", "") for s in steps)
    assert "decoy --version" in run_bodies, "smoke cell 1 (--version) missing"
    assert "decoy demo --json" in run_bodies, "smoke cell 2 (demo --json) missing"
    assert "decoy run" in run_bodies, "smoke cell 3 (decoy run) missing"
    assert "decoy templates show minimal" in run_bodies, (
        "the run cell must source its pipeline from the bundled minimal "
        "template, not from examples/ (which is repo-only, not in the wheel)"
    )


def test_release_smoke_workflow_does_not_publish() -> None:
    """OSS.1 is a smoke gate, not a publish pipeline. Any real publish
    action here is a scope violation; publishing belongs to OSS.7.

    The check scans the EXECUTABLE step bodies, not comments / docs.
    Mentioning PyPI in a comment that explains the eventual transition
    is fine; running `twine upload` is not."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = data["jobs"]["fresh-install"]
    run_bodies = "\n".join(s.get("run", "") for s in job["steps"]).lower()
    assert "twine upload" not in run_bodies, (
        "OSS.1 must not publish; twine upload belongs to OSS.7"
    )
    assert "upload-pypi" not in run_bodies, (
        "OSS.1 must not publish; the trusted-publish action belongs to OSS.7"
    )
