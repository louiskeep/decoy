"""The gate's view of the typed side files (`--vault`, `--evidence-out`) in `layout_issues`.

A NUL byte cannot arrive through a real command line (the option parser refuses it first), so
the typed-file NUL cell is held here against `layout_issues` itself, which every route calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from decoy.cli.io import OutputPlacement
from decoy.cli.io._placement import layout_issues, resolved_output_collisions

ESCAPES = "layout.output_path_escapes"
COLLISION = "layout.output_path_collision"


def _config() -> dict:
    return {"targets": {"a": {"type": "file", "format": "csv", "path": "m.csv"}}}


@pytest.mark.parametrize("flag", ["--vault", "--evidence-out"])
def test_a_nul_in_a_typed_side_file_is_an_escape_refusal(tmp_path: Path, flag: str) -> None:
    yaml = tmp_path / "pipeline.yaml"
    yaml.write_text("x: 1\n", encoding="utf-8")
    placement = OutputPlacement.fixed(tmp_path / "build", ((flag, tmp_path / "t\x00.bin"),))
    issues = layout_issues(yaml, _config(), placement)
    assert [err.code for _loc, err in issues] == [ESCAPES]
    assert "t\x00" not in issues[0][1].message
    assert flag in issues[0][1].message


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")
def test_a_dangling_symlink_collides_with_its_target_in_the_one_collision_rule(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.csv"
    (tmp_path / "alias.csv").symlink_to(real)
    config = {
        "targets": {
            "a": {"type": "file", "format": "csv", "path": str(tmp_path / "alias.csv")},
            "b": {"type": "file", "format": "csv", "path": str(real)},
        }
    }
    assert resolved_output_collisions(config, None) == ("targets.a.path", "targets.b.path")
    assert not real.exists()
