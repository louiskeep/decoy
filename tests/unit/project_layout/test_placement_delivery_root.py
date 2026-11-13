"""DELIV C1: the single-root rule (AT-22 to AT-24) and side files out of `out/` (AT-47).

The gate refuses before any row is read, so every case runs `layout_issues`, the one check
`validate`, `ci check` and `run` share.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from decoy.cli.io import OutputPlacement
from decoy.cli.io._placement import (
    _destination_is_within,
    _folds_case,
    layout_issues,
    replaces_final,
)

SPLIT = "layout.delivery_root_split"
IN_OUT = "layout.side_file_in_out"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    yaml = root / "pipelines" / "p.yaml"
    yaml.parent.mkdir()
    yaml.write_text("name: p\n", encoding="utf-8")
    return root, yaml


def _targets(**paths: str) -> dict:
    return {"targets": {t: {"type": "file", "format": "csv", "path": p} for t, p in paths.items()}}


def _codes(issues: list) -> list[str]:
    return [err.code for _loc, err in issues]


@pytest.mark.parametrize("mode", ["strict", "best_effort"])
def test_at22_at24_one_relative_and_one_absolute_target_is_split(tmp_path: Path, mode: str) -> None:
    root, yaml = _project(tmp_path)
    config = {"delivery": {"mode": mode}, **_targets(a="a.csv", b=str(tmp_path / "b.csv"))}
    issues = layout_issues(yaml, config)
    assert _codes(issues) == [SPLIT]
    message = issues[0][1].message
    assert "targets.a.path" in message and "targets.b.path" in message
    assert str(tmp_path) not in message
    assert not (root / "out").exists()


def test_two_absolute_targets_in_two_folders_are_split(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    config = _targets(a=str(tmp_path / "x" / "a.csv"), b=str(tmp_path / "y" / "b.csv"))
    assert _codes(layout_issues(tmp_path / "p.yaml", config)) == [SPLIT]


def test_a_relative_and_an_absolute_target_are_split_under_out_dir(tmp_path: Path) -> None:
    placement = OutputPlacement.fixed(tmp_path / "build")
    config = _targets(a="a.csv", b=str(tmp_path / "b.csv"))
    assert _codes(layout_issues(tmp_path / "p.yaml", config, placement)) == [SPLIT]


def test_a_relative_and_an_absolute_target_in_the_out_dir_folder_share_it(tmp_path: Path) -> None:
    build = tmp_path / "build"
    placement = OutputPlacement.fixed(build)
    config = _targets(a="a.csv", b=str(build / "b.csv"))
    assert layout_issues(tmp_path / "p.yaml", config, placement) == []


def test_relative_targets_alone_and_a_quarantine_beside_them_are_one_root(tmp_path: Path) -> None:
    _root, yaml = _project(tmp_path)
    config = {
        **_targets(a="a.csv", b="b.csv"),
        "quarantine": {"enabled": True, "output_path": "q.csv"},
    }
    assert layout_issues(yaml, config) == []


def test_a_quarantine_outside_the_absolute_folder_is_split(tmp_path: Path) -> None:
    config = {
        **_targets(a=str(tmp_path / "a.csv")),
        "quarantine": {"enabled": True, "output_path": "q.csv"},
    }
    assert _codes(layout_issues(tmp_path / "p.yaml", config)) == [SPLIT]


@posix_only
def test_at23_two_absolute_targets_in_one_folder_through_a_symlink_are_accepted(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real)
    config = _targets(a=str(real / "a.csv"), b=str(tmp_path / "alias" / "b.csv"))
    assert layout_issues(tmp_path / "p.yaml", config) == []


@pytest.mark.parametrize(
    "rel",
    [
        "out/p/LATEST",
        "out/p/current/x.json",
        "out/p/x.json",
        "out/other/x.json",
        "out/x.json",
    ],
)
@pytest.mark.parametrize("flag", ["--evidence-out", "--vault"])
def test_at47_a_side_file_under_out_is_refused(tmp_path: Path, rel: str, flag: str) -> None:
    root, yaml = _project(tmp_path)
    placement = OutputPlacement(typed=((flag, root / rel),))
    issues = layout_issues(yaml, _targets(a="a.csv"), placement)
    assert _codes(issues) == [IN_OUT]
    assert flag in issues[0][1].message and "out/" in issues[0][1].message
    assert str(tmp_path) not in issues[0][1].message
    assert not (root / "out").exists()


@posix_only
def test_at47_a_symlink_alias_of_an_out_folder_is_refused(tmp_path: Path) -> None:
    root, yaml = _project(tmp_path)
    (root / "out" / "p").mkdir(parents=True)
    (root / "alias").symlink_to(root / "out" / "p")
    placement = OutputPlacement(typed=(("--vault", root / "alias" / "v.db"),))
    assert _codes(layout_issues(yaml, _targets(a="a.csv"), placement)) == [IN_OUT]


def test_at47_a_case_variant_of_out_is_refused_where_the_filesystem_folds(tmp_path: Path) -> None:
    root, yaml = _project(tmp_path)
    (root / "out").mkdir()
    if not (root / "OUT").exists():
        pytest.skip("case-sensitive filesystem")
    placement = OutputPlacement(typed=(("--vault", root / "OUT" / "v.db"),))
    assert _codes(layout_issues(yaml, _targets(a="a.csv"), placement)) == [IN_OUT]


def test_at47_a_case_variant_of_a_missing_out_is_refused_by_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Runs on every OS: a string prefix test cannot match "OUT" to "out", identity can.
    monkeypatch.setattr("decoy.cli.io._placement._folds_case", lambda _folder: True)
    root, yaml = _project(tmp_path)
    placement = OutputPlacement(typed=(("--vault", root / "OUT" / "v.db"),))
    assert _codes(layout_issues(yaml, _targets(a="a.csv"), placement)) == [IN_OUT]


@posix_only
def test_at47_a_final_link_under_out_is_judged_by_where_it_sits(tmp_path: Path) -> None:
    root, yaml = _project(tmp_path)
    (root / "out").mkdir()
    (root / "elsewhere.json").write_text("{}", encoding="utf-8")
    (root / "out" / "e.json").symlink_to(root / "elsewhere.json")
    placement = OutputPlacement(typed=(("--evidence-out", root / "out" / "e.json"),))
    assert _codes(layout_issues(yaml, _targets(a="a.csv"), placement)) == [IN_OUT]


def test_at47_side_files_beside_out_or_elsewhere_are_accepted(tmp_path: Path) -> None:
    root, yaml = _project(tmp_path)
    typed = (("--vault", root / "v.db"), ("--evidence-out", root / "outside" / "e.json"))
    assert layout_issues(yaml, _targets(a="a.csv"), OutputPlacement(typed=typed)) == []


def test_at47_the_same_flags_inside_a_fixed_out_dir_are_accepted(tmp_path: Path) -> None:
    root, yaml = _project(tmp_path)
    build = root / "out" / "build"
    placement = OutputPlacement.fixed(build, (("--vault", build / "v.db"),))
    assert layout_issues(yaml, _targets(a="a.csv"), placement) == []


def test_destination_is_within_uses_only_the_destination_key(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    assert _destination_is_within(tmp_path / "d" / "x" / "y.txt", tmp_path / "d")
    assert _destination_is_within(tmp_path / "d", tmp_path / "d")
    assert not _destination_is_within(tmp_path / "e" / "y.txt", tmp_path / "d")


def test_the_final_link_policy_is_one_declared_mapping() -> None:
    assert replaces_final("--vault")
    assert not replaces_final("--evidence-out")
    assert not replaces_final("targets.a.path")
    assert not replaces_final("quarantine.path")


@posix_only
def test_at47_an_evidence_link_outside_out_that_lands_in_out_is_refused(tmp_path: Path) -> None:
    # --evidence-out follows a final link, so the bytes would overwrite old.csv in out/.
    root, yaml = _project(tmp_path)
    victim = root / "out" / "p" / "old.csv"
    victim.parent.mkdir(parents=True)
    victim.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "ev.json"
    link.symlink_to(victim)
    placement = OutputPlacement(typed=(("--evidence-out", link),))
    issues = layout_issues(yaml, _targets(a="a.csv"), placement)
    assert _codes(issues) == [IN_OUT]
    assert str(tmp_path) not in issues[0][1].message
    assert victim.read_text(encoding="utf-8") == "keep\n"


@posix_only
def test_at47_a_vault_link_outside_out_is_replaced_not_followed_so_it_is_accepted(
    tmp_path: Path,
) -> None:
    root, yaml = _project(tmp_path)
    victim = root / "out" / "p" / "old.csv"
    victim.parent.mkdir(parents=True)
    victim.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "v.db"
    link.symlink_to(victim)
    placement = OutputPlacement(typed=(("--vault", link),))
    assert layout_issues(yaml, _targets(a="a.csv"), placement) == []
    assert victim.read_text(encoding="utf-8") == "keep\n"


@posix_only
def test_at22_a_final_link_to_another_folder_splits_two_absolute_targets(tmp_path: Path) -> None:
    here, there = tmp_path / "here", tmp_path / "there"
    here.mkdir()
    there.mkdir()
    (here / "b.csv").symlink_to(there / "b.csv")
    config = _targets(a=str(here / "a.csv"), b=str(here / "b.csv"))
    assert _codes(layout_issues(tmp_path / "p.yaml", config)) == [SPLIT]


@posix_only
def test_at23_final_links_landing_in_one_folder_share_a_root_across_declared_folders(
    tmp_path: Path,
) -> None:
    one, two, shared = tmp_path / "one", tmp_path / "two", tmp_path / "shared"
    for folder in (one, two, shared):
        folder.mkdir()
    (one / "a.csv").symlink_to(shared / "x.csv")
    (two / "b.csv").symlink_to(shared / "y.csv")
    config = _targets(a=str(one / "a.csv"), b=str(two / "b.csv"))
    assert layout_issues(tmp_path / "p.yaml", config) == []


@pytest.mark.parametrize(
    ("platform", "folds"), [("win32", True), ("darwin", True), ("linux", False)]
)
def test_a_folder_with_no_letters_uses_the_platform_default(
    monkeypatch: pytest.MonkeyPatch, platform: str, folds: bool
) -> None:
    monkeypatch.setattr("decoy.cli.io._placement.sys.platform", platform)
    assert _folds_case(Path("/123/456")) is folds


def test_case_folding_is_probed_for_real_when_a_component_has_letters(tmp_path: Path) -> None:
    folder = tmp_path / "Probe"
    folder.mkdir()
    assert _folds_case(folder) == (tmp_path / "pROBE").exists()
