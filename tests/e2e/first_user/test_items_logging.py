"""No stray `logs/decoy_engine.log` in the user's working directory.

The engine used to default its log file to `logs/decoy_engine.log` under the cwd, so a first
`decoy scan` left a `logs/` folder behind. Each command runs in a fresh process so the engine's
lazy logger starts from its defaults.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qa_first_user"


def _decoy(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "DECOY_DEBUG"}
    # The fixture hashes its key column, and a keyed strategy needs a mask secret.
    env["DECOY_TEST_MASK_SECRET"] = "ab" * 32
    return subprocess.run(
        [sys.executable, "-m", "decoy", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.fixture
def staged(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    data.mkdir()
    for fixture in ("patients.csv", "visits.csv", "pipeline_namespaced.yaml"):
        shutil.copy(_FIXTURES / fixture, data / fixture)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    return data, cwd


@pytest.mark.parametrize("command", ["scan", "demo", "run"])
def test_no_logs_folder_in_an_empty_cwd(staged: tuple[Path, Path], command: str) -> None:
    data, cwd = staged
    args = {
        "scan": ["scan", str(data / "patients.csv"), "--has-header"],
        "demo": ["demo", "--dir", str(data / "demo")],
        "run": [
            "run",
            str(data / "pipeline_namespaced.yaml"),
            "--mask-secret",
            "env:DECOY_TEST_MASK_SECRET",
        ],
    }[command]
    result = _decoy(args, cwd)
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in cwd.iterdir()) == []
