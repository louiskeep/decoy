"""AT-11 (P2a): a file in a run folder keeps its declared format, and so does the old place.

`owning_run` finds the run folder `<root>/out/<name>/<run-id>/` that holds a file, following
`latest`. `input_format` then treats a file at the placed target, or at the old YAML-folder
target, as the declared target. Any other path still takes the suffix rule.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from decoy.cli.io import _targets
from decoy.cli.io._layout import RunFolder, is_run_id, owning_run, placed_path
from decoy.cli.io._targets import input_format

RUN_ID = "20261109T101500123456Z-0a1b2c3d"
LAYOUT = {"columns": [{"name": "a", "type": "int", "width": 4}]}


def _config(path: str = "masked.dat") -> dict:
    return {
        "targets": {"t": {"type": "file", "format": "fixed_width", "path": path, "layout": LAYOUT}}
    }


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, tuple[Path, str], Path]:
    root = tmp_path / "proj"
    run = root / "out" / "orders" / RUN_ID
    run.mkdir(parents=True)
    return root, (root, "orders"), run


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def test_owning_run_finds_the_run_folder(project: tuple[Path, tuple[Path, str], Path]) -> None:
    _, ref, run = project
    found = owning_run(_touch(run / "masked.dat"), *ref)
    assert found is not None
    assert found.path == run.resolve()
    assert found.run_id == RUN_ID


def test_owning_run_finds_a_nested_file(project: tuple[Path, tuple[Path, str], Path]) -> None:
    _, ref, run = project
    assert owning_run(_touch(run / "sub" / "m.dat"), *ref) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="latest is a symlink on POSIX only")
def test_owning_run_follows_latest(project: tuple[Path, tuple[Path, str], Path]) -> None:
    root, ref, run = project
    _touch(run / "masked.dat")
    os.symlink(RUN_ID, root / "out" / "orders" / "latest")
    found = owning_run(root / "out" / "orders" / "latest" / "masked.dat", *ref)
    assert found is not None and found.run_id == RUN_ID


def test_owning_run_refuses_other_places(project: tuple[Path, tuple[Path, str], Path]) -> None:
    root, ref, _ = project
    cases = [
        _touch(root / "masked.dat"),  # old YAML-folder place
        _touch(root / "out" / "orders" / "masked.dat"),  # pipeline folder, no run id
        _touch(root / "out" / "other" / RUN_ID / "masked.dat"),  # another pipeline
        _touch(root / "out" / "orders" / "not-a-run" / "masked.dat"),  # not a run id
        _touch(root / "elsewhere" / "out" / "orders" / RUN_ID / "masked.dat"),
    ]
    for case in cases:
        assert owning_run(case, *ref) is None


def test_owning_run_refuses_the_run_folder_itself(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    _, ref, run = project
    assert owning_run(run, *ref) is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_owning_run_refuses_a_link_leaving_the_run(
    project: tuple[Path, tuple[Path, str], Path], tmp_path: Path
) -> None:
    _, ref, run = project
    outside = _touch(tmp_path / "outside" / "masked.dat")
    os.symlink(outside, run / "masked.dat")
    assert owning_run(run / "masked.dat", *ref) is None


def test_old_yaml_folder_path_keeps_the_declared_layout(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, _ = project
    old = _touch(root / "masked.dat")
    expected = ("fixed_width", LAYOUT)
    assert input_format(_config(), "t", old, root) == expected
    assert input_format(_config(), "t", old, root, pipeline=ref) == expected


def test_run_folder_path_keeps_the_declared_layout(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, run = project
    placed = _touch(run / "masked.dat")
    assert input_format(_config(), "t", placed, root, pipeline=ref) == ("fixed_width", LAYOUT)


def test_nested_declared_path_in_a_run_folder(project: tuple[Path, tuple[Path, str], Path]) -> None:
    root, ref, run = project
    placed = _touch(run / "sub" / "m.dat")
    assert input_format(_config("sub/m.dat"), "t", placed, root, pipeline=ref) == (
        "fixed_width",
        LAYOUT,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="latest is a symlink on POSIX only")
def test_latest_path_keeps_the_declared_layout(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, run = project
    _touch(run / "masked.dat")
    os.symlink(RUN_ID, root / "out" / "orders" / "latest")
    via_latest = root / "out" / "orders" / "latest" / "masked.dat"
    assert input_format(_config(), "t", via_latest, root, pipeline=ref) == ("fixed_width", LAYOUT)


def test_other_files_in_a_run_folder_take_the_suffix_rule(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, run = project
    stray = _touch(run / "notes.csv")
    assert input_format(_config(), "t", stray, root, pipeline=ref) == ("csv", None)


def test_without_a_ref_a_run_folder_file_is_not_the_target(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, _, run = project
    placed = _touch(run / "masked.dat")
    assert input_format(_config(), "t", placed, root) == ("csv", None)


def test_a_run_folder_file_of_another_pipeline_is_not_the_target(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, _ = project
    foreign = _touch(root / "out" / "other" / RUN_ID / "masked.dat")
    assert input_format(_config(), "t", foreign, root, pipeline=ref) == ("csv", None)


def test_undeclared_format_in_a_run_folder_is_refused(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, run = project
    config = {"targets": {"t": {"type": "file", "path": "masked.dat"}}}
    placed = _touch(run / "masked.dat")
    with pytest.raises(_targets.TargetFormatError) as err:
        input_format(config, "t", placed, root, pipeline=ref)
    assert err.value.code == _targets.UNREADABLE
    assert "masked.dat" not in str(err.value)
    assert err.value.__cause__ is None and err.value.__context__ is None


def test_a_climb_into_another_run_is_not_the_target(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, _ = project
    other = "20260101T000000000000Z-ffffffff"
    sibling = _touch(root / "out" / "orders" / other / "x.dat")
    config = _config(f"../{other}/x.dat")
    assert input_format(config, "t", sibling, root, pipeline=ref) == ("csv", None)


def test_placed_path_stays_inside_the_run() -> None:
    run = RunFolder(Path("/p/out/orders") / RUN_ID, RUN_ID)
    assert placed_path(run, "m.dat") == run.path / "m.dat"
    assert placed_path(run, "sub/../m.dat") == run.path / "m.dat"
    for raw in (
        "/abs/m.dat",
        "../m.dat",
        f"../{RUN_ID}x/m.dat",
        "..",
        ".",
        "sub/../..",
        f"../{RUN_ID}/m.dat",
    ):
        assert placed_path(run, raw) is None


@pytest.mark.parametrize("hexpart", ["0a1b2c3d", "0a1b2c3d4e5f", "0" * 32])
def test_run_id_accepts_8_to_32_hex_in_steps_of_four(hexpart: str) -> None:
    assert is_run_id(f"20261109T101500123456Z-{hexpart}")


@pytest.mark.parametrize(
    "value",
    [
        "20261109T101500123456Z-" + "a" * 9,
        "20261109T101500123456Z-" + "a" * 33,
        "20261109T101500123456Z-0A1B2C3D",
        "20261109T10150012345Z-0a1b2c3d",
        "20261109T101500123456Z-0a1b2c3",
        "20261109T101500123456Z-0a1b2c3d\n",
        "latest",
        "",
    ],
)
def test_run_id_rejects_malformed(value: str) -> None:
    assert not is_run_id(value)


def _run_folder(run: Path) -> RunFolder:
    return RunFolder(run.resolve(), RUN_ID)


@pytest.mark.parametrize("raw", ["\\x", "C:x", "C:\\x", "//server/share/x", "c:/x", "/x"])
def test_placed_path_refuses_anchors_and_drives(raw: str) -> None:
    run = RunFolder(Path("/p/out/orders") / RUN_ID, RUN_ID)
    assert placed_path(run, raw) is None


@pytest.mark.parametrize("raw", ["sub/", "sub\\", "a/b/"])
def test_placed_path_refuses_directory_like_targets(raw: str) -> None:
    run = RunFolder(Path("/p/out/orders") / RUN_ID, RUN_ID)
    assert placed_path(run, raw) is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_placed_path_refuses_a_symlink_ancestor_leaving_the_run(
    project: tuple[Path, tuple[Path, str], Path], tmp_path: Path
) -> None:
    _, _, run = project
    (tmp_path / "outside").mkdir()
    os.symlink(tmp_path / "outside", run / "link")
    assert placed_path(_run_folder(run), "link/value.csv") is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_a_symlink_ancestor_inside_the_run_keeps_the_declared_layout(
    project: tuple[Path, tuple[Path, str], Path],
) -> None:
    root, ref, run = project
    (run / "real").mkdir()
    os.symlink("real", run / "link")
    target = _touch(run / "real" / "m.dat")
    placed = placed_path(_run_folder(run), "link/m.dat")
    assert placed == target.resolve()
    config = _config("link/m.dat")
    assert input_format(config, "t", target, root, pipeline=ref) == ("fixed_width", LAYOUT)
    assert input_format(config, "t", run / "link" / "m.dat", root, pipeline=ref) == (
        "fixed_width",
        LAYOUT,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_a_symlink_ancestor_leaving_the_run_is_not_the_target(
    project: tuple[Path, tuple[Path, str], Path], tmp_path: Path
) -> None:
    root, ref, run = project
    outside = tmp_path / "outside"
    os.symlink(outside, run / "link")
    target = _touch(outside / "value.dat")
    config = _config("link/value.dat")
    assert input_format(config, "t", target, root, pipeline=ref) == ("csv", None)
