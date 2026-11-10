"""AT-2, AT-5, AT-15 and AT-17: pipeline names and claims, run ids and folders, `out/`, budget.

Unit cells for the services P2b builds `RunLayout` on. The engine owns the name rule
(`is_valid_pipeline_name`); the CLI cells here prove the CLI asks it and never copies it.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import stat
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from decoy_engine import is_valid_pipeline_name

from decoy import _private_file
from decoy._atomic import AtomicWriteError
from decoy._private_file import PRIVATE_EXISTS, PRIVATE_MODE_FAILED, PrivateFileError
from decoy.cli.io import (
    LayoutError,
    _layout,
    check_path_budget,
    create_run_folder,
    is_run_id,
    name_dir,
    new_run_id,
    pipeline_name_for,
    prepare_out,
    read_claim,
    write_claim,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX modes")
RUN_ID_RULE = r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}"
START = datetime(2026, 11, 9, 10, 15, 0, 123456, tzinfo=timezone.utc)
INVOCATION = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proj"
    (folder / "pipelines").mkdir(parents=True)
    return folder


def _yaml(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("version: 2\n", encoding="utf-8")
    return path


def _hash6(rel: str) -> str:
    return hashlib.sha256(rel.encode()).hexdigest()[:6]


# -- AT-2: names ---------------------------------------------------------------------------


def test_a_pipelines_folder_gives_its_own_name(root: Path) -> None:
    got = pipeline_name_for(root, _yaml(root, "pipelines/members-mask/pipeline.yaml"), None)
    assert (got.name, got.firm, got.yaml_rel) == (
        "members-mask",
        True,
        "pipelines/members-mask/pipeline.yaml",
    )


def test_a_matching_declared_name_is_accepted_and_a_differing_one_is_a_mismatch(
    root: Path,
) -> None:
    path = _yaml(root, "pipelines/orders/pipeline.yaml")
    assert pipeline_name_for(root, path, "orders").name == "orders"
    with pytest.raises(LayoutError) as exc:
        pipeline_name_for(root, path, "sales")
    assert exc.value.code == "layout.pipeline_name_mismatch"


@pytest.mark.parametrize("folder", ["bad name", "-x", ".hidden", "a" * 65, "CON", "x."])
def test_an_invalid_pipelines_folder_is_refused(root: Path, folder: str) -> None:
    path = _yaml(root, f"pipelines/{folder}/pipeline.yaml")
    with pytest.raises(LayoutError) as exc:
        pipeline_name_for(root, path, None)
    assert exc.value.code == "layout.pipeline_name_invalid"


@pytest.mark.parametrize(
    "declared", ["bad name", "orders\n", "CON", "aux.v1", "COM¹", "x.", True, 7, 1.5, ["a"]]
)
def test_an_invalid_or_non_string_declared_name_is_refused_without_coercion(
    root: Path, declared: object
) -> None:
    path = _yaml(root, "jobs/j.yaml")
    with pytest.raises(LayoutError) as exc:
        pipeline_name_for(root, path, declared)
    assert exc.value.code == "layout.pipeline_name_invalid"


@pytest.mark.parametrize("declared", ["COM0", "LPT0", "orders", "a.b-c_d"])
def test_com0_and_lpt0_are_not_reserved(root: Path, declared: str) -> None:
    got = pipeline_name_for(root, _yaml(root, "jobs/j.yaml"), declared)
    assert got.name == declared
    assert got.firm


def test_a_stem_that_changes_in_the_slug_takes_the_path_hash(root: Path) -> None:
    got = pipeline_name_for(root, _yaml(root, "jobs/My Pipeline.yaml"), None)
    assert got.name == f"My-Pipeline-{_hash6('jobs/My Pipeline.yaml')}"
    assert not got.firm


def test_a_windows_device_stem_takes_the_path_hash(root: Path) -> None:
    got = pipeline_name_for(root, _yaml(root, "jobs/CON.yaml"), None)
    assert got.name == f"CON-{_hash6('jobs/CON.yaml')}"


def test_a_clean_stem_is_the_name(root: Path) -> None:
    assert pipeline_name_for(root, _yaml(root, "jobs/nightly.yaml"), None).name == "nightly"


def test_the_cli_and_the_engine_agree_on_a_generated_set(root: Path) -> None:
    rng = random.Random(20261109)
    alphabet = string.ascii_letters + string.digits + "_.- \n/¹é"
    for _ in range(400):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 70)))
        try:
            got = pipeline_name_for(root, _yaml(root, "jobs/p.yaml"), text)
        except LayoutError as exc:
            assert exc.code == "layout.pipeline_name_invalid"
            assert not is_valid_pipeline_name(text)
        else:
            assert is_valid_pipeline_name(text)
            assert got.name == text


def test_every_derived_name_passes_the_rule(root: Path) -> None:
    rng = random.Random(7)
    alphabet = string.ascii_letters + string.digits + "_.- /¹é()"
    stems = ["CON", "aux.v1", "LPT3.txt", "_x", "-", "", ".", "..", "a" * 120, "x." * 40]
    for _ in range(300):
        stems.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 90))))
    for stem in stems:
        rel = f"jobs/{stem or 'e'}.yaml"
        if "/" in stem or not stem:
            continue
        got = pipeline_name_for(root, root / rel, None)
        assert is_valid_pipeline_name(got.name), (stem, got.name)
        assert len(got.name) <= 64


# -- claims --------------------------------------------------------------------------------


def _claim(root: Path, name: str, yaml_rel: str) -> str | None:
    out, _ = prepare_out(root)
    return write_claim(name_dir(out, name), yaml_rel)


def test_the_first_run_writes_the_claim_and_the_same_yaml_passes_again(root: Path) -> None:
    assert _claim(root, "orders", "jobs/orders.yaml") is None
    assert read_claim(root / "out", "orders") == "jobs/orders.yaml"
    assert _claim(root, "orders", "jobs/orders.yaml") is None


def test_a_claim_held_by_another_yaml_is_reported(root: Path) -> None:
    _claim(root, "orders", "jobs/orders.yaml")
    assert _claim(root, "orders", "other/orders.yaml") == "jobs/orders.yaml"
    assert read_claim(root / "out", "orders") == "jobs/orders.yaml"


def test_a_second_yaml_declaring_a_claimed_name_is_a_collision(root: Path) -> None:
    _claim(root, "orders", "jobs/a.yaml")
    with pytest.raises(LayoutError) as exc:
        pipeline_name_for(root, _yaml(root, "jobs/b.yaml"), "orders")
    assert exc.value.code == "layout.pipeline_name_collision"
    assert "jobs/a.yaml" in exc.value.message
    assert "out/orders/PIPELINE" in exc.value.message


def test_a_second_yaml_deriving_a_claimed_name_gets_the_hash_suffix(root: Path) -> None:
    _claim(root, "orders", "jobs/orders.yaml")
    got = pipeline_name_for(root, _yaml(root, "more/orders.yaml"), None)
    assert got.name == f"orders-{_hash6('more/orders.yaml')}"
    assert pipeline_name_for(root, root / "jobs/orders.yaml", None).name == "orders"


def test_a_pipelines_folder_name_is_reserved_before_its_first_run(root: Path) -> None:
    _yaml(root, "pipelines/orders/pipeline.yaml")
    derived = pipeline_name_for(root, _yaml(root, "jobs/orders.yaml"), None)
    assert derived.name == f"orders-{_hash6('jobs/orders.yaml')}"
    with pytest.raises(LayoutError) as exc:
        pipeline_name_for(root, root / "jobs/orders.yaml", "orders")
    assert exc.value.code == "layout.pipeline_name_collision"


def test_a_pipelines_run_finds_a_claim_made_by_another_yaml(root: Path) -> None:
    _claim(root, "orders", "jobs/orders.yaml")
    member = _yaml(root, "pipelines/orders/pipeline.yaml")
    got = pipeline_name_for(root, member, None)
    assert got.name == "orders"
    assert write_claim(name_dir(root / "out", "orders"), got.yaml_rel) == "jobs/orders.yaml"


def test_a_mount_without_hard_links_is_the_atomic_error(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")

    def refuse(*_a: object, **_k: object) -> bool:
        raise AtomicWriteError("atomic_noclobber_unsupported")

    monkeypatch.setattr(_layout, "write_atomic", refuse)
    with pytest.raises(AtomicWriteError) as exc:
        write_claim(folder, "jobs/orders.yaml")
    assert exc.value.code == "atomic_noclobber_unsupported"


def test_no_temp_file_is_left_by_a_lost_claim(root: Path) -> None:
    _claim(root, "orders", "jobs/a.yaml")
    _claim(root, "orders", "jobs/b.yaml")
    assert sorted(p.name for p in (root / "out" / "orders").iterdir()) == ["PIPELINE"]


@posix_only
def test_an_out_folder_that_is_a_link_leaving_the_project_is_refused(
    root: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "out").symlink_to(elsewhere)
    with pytest.raises(LayoutError) as exc:
        prepare_out(root)
    assert exc.value.code == "layout.output_path_escapes"
    assert list(elsewhere.iterdir()) == []


@posix_only
def test_a_name_folder_that_is_a_link_leaving_out_is_refused(root: Path, tmp_path: Path) -> None:
    out, _ = prepare_out(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / "orders").symlink_to(elsewhere)
    with pytest.raises(LayoutError) as exc:
        name_dir(out, "orders")
    assert exc.value.code == "layout.output_path_escapes"


# -- AT-5: run ids -------------------------------------------------------------------------


def test_a_run_id_matches_the_rule_and_the_shared_parser() -> None:
    run_id = new_run_id(START, INVOCATION)
    assert re.fullmatch(RUN_ID_RULE, run_id)
    assert is_run_id(run_id)
    assert run_id == "20261109T101500123456Z-0a1b2c3d"
    assert len(new_run_id(START, INVOCATION, 6)) == 55


def test_a_run_id_is_in_utc_whatever_the_start_zone() -> None:
    zone = timezone(timedelta(hours=-5))
    local = START.astimezone(zone)
    assert new_run_id(local, INVOCATION) == new_run_id(START, INVOCATION)


def test_every_extra_block_length_is_a_run_id() -> None:
    for blocks in range(7):
        assert is_run_id(new_run_id(START, str(uuid.uuid4()), blocks))


def test_two_starts_in_one_second_sort_by_their_fractional_digits() -> None:
    first = new_run_id(START.replace(microsecond=9), INVOCATION)
    second = new_run_id(START.replace(microsecond=10), INVOCATION)
    third = new_run_id(START.replace(microsecond=999_999), "f" * 32)
    assert first < second < third


@posix_only
def test_a_run_folder_is_new_and_a_clash_takes_four_more_digits(root: Path) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")
    one = create_run_folder(folder, START, INVOCATION)
    two = create_run_folder(folder, START, INVOCATION)
    assert one.run_id == "20261109T101500123456Z-0a1b2c3d"
    assert two.run_id == "20261109T101500123456Z-0a1b2c3d4e5f"
    assert one.path.is_dir()
    assert two.path.is_dir()
    assert one.path != two.path


@posix_only
def test_running_out_of_digits_is_an_exists_error_not_a_reuse(root: Path) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")
    for blocks in range(7):
        (folder / new_run_id(START, INVOCATION, blocks)).mkdir()
    with pytest.raises(PrivateFileError) as exc:
        create_run_folder(folder, START, INVOCATION)
    assert exc.value.code == PRIVATE_EXISTS


def test_a_planted_link_at_the_run_id_is_a_clash_not_followed(root: Path, tmp_path: Path) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (folder / new_run_id(START, INVOCATION)).symlink_to(elsewhere)
    made = create_run_folder(folder, START, INVOCATION)
    assert made.run_id.endswith("4e5f")
    assert list(elsewhere.iterdir()) == []


# -- AT-15: out/ and the owner-only run folder ---------------------------------------------


def test_out_gitignore_holds_a_star_even_when_the_user_made_out_by_hand(root: Path) -> None:
    (root / "out").mkdir()
    out, warnings = prepare_out(root)
    assert warnings == ()
    assert (out / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_an_edited_out_gitignore_is_kept(root: Path) -> None:
    out, _ = prepare_out(root)
    (out / ".gitignore").write_text("*\n!keep.csv\n", encoding="utf-8")
    prepare_out(root)
    assert (out / ".gitignore").read_text(encoding="utf-8") == "*\n!keep.csv\n"


def test_an_unwritable_out_gitignore_warns_and_the_run_goes_on(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_a: object, **_k: object) -> bool:
        raise AtomicWriteError("atomic_write_failed", 13)

    monkeypatch.setattr(_layout, "write_local_target", refuse)
    out, warnings = prepare_out(root)
    assert out.is_dir()
    assert [w.code for w in warnings] == ["layout.gitignore_write_failed"]
    assert str(out / ".gitignore") in warnings[0].message


@posix_only
def test_a_run_folder_is_0700_under_umask_0_and_0777(root: Path) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")
    for mask in (0o000, 0o777):
        old = os.umask(mask)
        try:
            made = create_run_folder(folder, START, str(uuid.uuid4()))
        finally:
            os.umask(old)
        assert stat.S_IMODE(made.path.stat().st_mode) == 0o700


@posix_only
def test_a_mode_that_does_not_stick_fails_before_any_data_write_and_leaves_no_folder(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")

    def wide(fd: int, path: str, *, directory: bool = False) -> None:
        raise OSError(1, "mode did not stick")

    monkeypatch.setattr(_private_file, "restrict_owner_only", wide)
    with pytest.raises(PrivateFileError) as exc:
        create_run_folder(folder, START, INVOCATION)
    assert exc.value.code == PRIVATE_MODE_FAILED
    assert exc.value.__cause__ is None
    assert list(folder.iterdir()) == []


# -- AT-17: the Windows path budget --------------------------------------------------------


def _rel_for(folder: Path, total: int) -> str:
    return "a" * (total - len(str(folder)) - 1 - 55 - 1)


def test_a_placed_path_over_259_characters_is_refused_on_windows(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root / "out" / "orders"
    monkeypatch.setattr(_layout, "_on_windows", lambda: True)
    check_path_budget(folder, _rel_for(folder, 259))
    with pytest.raises(LayoutError) as exc:
        check_path_budget(folder, _rel_for(folder, 260))
    assert exc.value.code == "layout.path_too_long"
    assert "260" in exc.value.message


def test_the_same_path_passes_on_posix(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = root / "out" / "orders"
    monkeypatch.setattr(_layout, "_on_windows", lambda: False)
    check_path_budget(folder, _rel_for(folder, 400))


@posix_only
def test_a_fifo_at_the_claim_path_is_no_claim_and_does_not_block(root: Path) -> None:
    import threading

    out, _ = prepare_out(root)
    folder = name_dir(out, "orders")
    os.mkfifo(folder / "PIPELINE")
    result: list[str | None] = ["unset"]

    def probe() -> None:
        result[0] = read_claim(out, "orders")

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(10)
    assert not thread.is_alive(), "reading the claim blocked on a FIFO"
    assert result == [None]
