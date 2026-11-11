"""AT-3, AT-5, AT-6, AT-7 and AT-10 (P2b): `run` and `tokenize` write into a run folder.

A relative target lands at `out/<name>/<run-id>/<path>`; the run folder, the claim, `LATEST`
and the `current` link come from `RunLayout`. `demo` and `mask()` keep fixed paths. Table writes go through the one
writer in `cli/io/_targets.py`; these cells check where they land and what else is left behind.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from decoy.cli.io import (
    LayoutError,
    PipelineName,
    RunLayout,
    _layout,
    mint_invocation_id,
    write_targets,
)
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

runner = CliRunner()
RUN_ID_RULE = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}")
START = datetime(2026, 11, 9, 10, 15, 0, 123456, tzinfo=timezone.utc)
ORDERS = PipelineName("orders", True, "pipelines/orders/pipeline.yaml")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="current is a symlink on POSIX")


def _source(root: Path) -> Path:
    src = root / "a.csv"
    src.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"email": ["a@example.com", "b@example.com"]}).to_csv(src, index=False)
    return src


def _config(root: Path, **extra: object) -> dict:
    cfg: dict = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(_source(root))},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    cfg.update(extra)
    return cfg


def _write(root: Path, rel: str, cfg: dict) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    return root


def _runs(root: Path, name: str) -> list[Path]:
    folder = root / "out" / name
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if RUN_ID_RULE.fullmatch(p.name))


def _files_named(root: Path, name: str) -> list[Path]:
    return sorted(p for p in root.rglob(name) if p.is_file() or p.is_symlink())


def _run(cfg: Path, *args: str):
    return runner.invoke(app, ["run", str(cfg), *args])


def _open(root: Path, started: datetime | None = None, invocation: str | None = None) -> RunLayout:
    return RunLayout.open(root, ORDERS, invocation or mint_invocation_id(), started)


# --- AT-3 placement ----------------------------------------------------------------------


@pytest.mark.parametrize("chunked", [False, True])
def test_a_relative_target_lands_in_the_run_folder_and_nowhere_else(
    tmp_path: Path, chunked: bool
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    result = _run(cfg, *(["--chunked"] if chunked else []))
    assert result.exit_code == 0, result.output
    runs = _runs(root, "orders")
    assert len(runs) == 1
    assert _files_named(root, "masked.csv") == [runs[0] / "masked.csv"]
    assert not (cfg.parent / "masked.csv").exists()


def test_a_nested_relative_target_keeps_its_folders_inside_the_run(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg_dict = _config(root)
    cfg_dict["targets"]["a"]["path"] = "sub/dir/masked.csv"
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    assert _run(cfg).exit_code == 0
    (run,) = _runs(root, "orders")
    assert (run / "sub" / "dir" / "masked.csv").is_file()


def test_parquet_lands_in_the_run_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg_dict = _config(root)
    cfg_dict["targets"]["a"] = {"type": "file", "format": "parquet", "path": "masked.parquet"}
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    assert _run(cfg).exit_code == 0
    (run,) = _runs(root, "orders")
    assert (run / "masked.parquet").is_file()


def test_an_absolute_target_lands_at_its_path_with_no_out_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    target = tmp_path / "delivery" / "masked.csv"
    cfg_dict = _config(root)
    cfg_dict["targets"]["a"]["path"] = str(target)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    assert _run(cfg).exit_code == 0
    assert target.is_file()
    assert not (root / "out").exists()


def test_fixed_width_goes_through_the_layout(tmp_path: Path) -> None:
    layout = _open(_project(tmp_path))
    columns = {"columns": [{"name": "a", "start": 0, "width": 4, "type": "int", "align": "right"}]}
    config = {
        "targets": {
            "t": {"type": "file", "format": "fixed_width", "path": "m.dat", "layout": columns}
        }
    }
    written = write_targets(config, {"t": pa.table({"a": [1]})}, layout)
    assert layout.run is not None
    assert written == {"t": layout.run.path / "m.dat"}
    assert written["t"].is_file()


def test_an_escaping_target_is_refused_at_write_time_with_the_layout_code(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root)
    config = {"targets": {"t": {"type": "file", "format": "csv", "path": "../../x.csv"}}}
    with pytest.raises(LayoutError) as raised:
        write_targets(config, {"t": pa.table({"a": [1]})}, layout)
    assert raised.value.code == "layout.output_path_escapes"
    assert not (root / "x.csv").exists()


def test_tokenize_places_its_target_in_a_run_folder(tmp_path: Path, monkeypatch) -> None:
    from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    root = _project(tmp_path)
    cfg_dict = _config(root, global_settings={"seed": 3, "mask_secret_ref": TEST_MASK_SECRET_REF})
    cfg_dict["tables"][0]["columns"][0] = {
        "name": "email",
        "strategy": "tokenize",
        "namespace": "em",
    }
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")])
    assert result.exit_code == 0, result.output
    (run,) = _runs(root, "orders")
    assert _files_named(root, "masked.csv") == [run / "masked.csv"]


# --- AT-3 mask() keeps fixed paths ---------------------------------------------------------


def test_mask_with_no_out_writes_beside_the_config(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    cfg = _write(root, "pipeline.yaml", _config(root))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    decoy.mask(config=str(cfg))
    assert (root / "masked.csv").is_file()
    assert list(elsewhere.iterdir()) == []
    assert not (root / "out").exists()


def test_mask_out_is_relative_to_the_current_folder(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    cfg = _write(root, "pipeline.yaml", _config(root))
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    decoy.mask(config=str(cfg), out="o/masked.csv")
    assert (here / "o" / "masked.csv").is_file()
    assert not (root / "o").exists()
    assert not (root / "out").exists()


def test_mask_of_a_dict_writes_under_the_current_folder(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    decoy.mask(config=_config(root))
    assert (here / "masked.csv").is_file()
    assert not (here / "out").exists()


# --- AT-5 run id and invocation id --------------------------------------------------------


def test_the_run_folder_name_follows_the_run_id_rule(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root, START, "0a1b2c3d-4e5f-6789-abcd-ef0123456789")
    assert layout.run is not None
    assert RUN_ID_RULE.fullmatch(layout.run.run_id)
    assert layout.run.run_id == "20261109T101500123456Z-0a1b2c3d"
    assert layout.run.path == (root / "out" / "orders" / layout.run.run_id).resolve()


def test_a_forced_prefix_clash_gives_two_folders(tmp_path: Path) -> None:
    root = _project(tmp_path)
    invocation = str(uuid.uuid4())
    first, second = _open(root, START, invocation), _open(root, START, invocation)
    assert first.run is not None and second.run is not None
    assert first.run.path != second.run.path
    assert second.run.run_id.startswith(first.run.run_id)
    assert RUN_ID_RULE.fullmatch(second.run.run_id)


def test_two_starts_in_one_second_sort_by_their_fractional_digits(tmp_path: Path) -> None:
    root = _project(tmp_path)
    early = _open(root, START)
    late = _open(root, START + timedelta(microseconds=5))
    assert early.run is not None and late.run is not None
    assert early.run.run_id < late.run.run_id


def test_the_evidence_run_id_is_the_invocation_id_in_the_folder_name(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    evidence = tmp_path / "ev.json"
    result = _run(cfg, "--evidence-out", str(evidence))
    assert result.exit_code == 0, result.output
    run_id = json.loads(evidence.read_text(encoding="utf-8"))["run_id"]
    (run,) = _runs(root, "orders")
    assert run.name.endswith(uuid.UUID(run_id).hex[:8])


def test_evidence_for_an_unwritten_target_names_the_run_folder_not_the_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    """A chunked CSV whose stream yields nothing publishes nothing; a cwd file must not stand in."""
    import decoy_engine

    monkeypatch.setattr(decoy_engine, "run_mask_pipeline_chunked", lambda *a, **k: iter(()))
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "masked.csv").write_text("stale,unrelated\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    evidence = tmp_path / "ev.json"
    result = _run(cfg, "--chunked", "--evidence-out", str(evidence))
    assert result.exit_code == 0, result.output
    (run,) = _runs(root, "orders")
    entry = json.loads(evidence.read_text(encoding="utf-8"))["output_fingerprints"]["a"]
    assert entry["path"] == (run / "masked.csv").relative_to(root).as_posix()
    assert (entry["fingerprint"], entry["size_bytes"]) == (None, None)
    assert not (run / "masked.csv").exists()


def test_one_invocation_id_is_minted_per_command(tmp_path: Path, monkeypatch) -> None:
    from decoy.cli.run import _flow

    calls: list[str] = []

    def spy() -> str:
        calls.append(mint_invocation_id())
        return calls[-1]

    monkeypatch.setattr(_flow, "mint_invocation_id", spy)
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    assert _run(cfg).exit_code == 0
    assert len(calls) == 1


# --- AT-6 latest --------------------------------------------------------------------------


def test_a_clean_run_moves_latest(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    assert _run(cfg).exit_code == 0
    (run,) = _runs(root, "orders")
    assert (root / "out" / "orders" / "LATEST").read_text(encoding="utf-8").strip() == run.name


def test_the_latest_file_and_link_names_do_not_fold_together() -> None:
    """macOS and Windows fold case by default, so `LATEST` and the link need distinct names."""
    assert _layout._LATEST_FILE.casefold() != _layout._LATEST_LINK.casefold()


def test_no_two_names_in_the_pipeline_folder_fold_together(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root, START)
    assert layout.commit_latest() == ()
    names = os.listdir(root / "out" / "orders")
    assert "LATEST" in names
    assert len({n.casefold() for n in names}) == len(names), sorted(names)


@posix_only
def test_current_is_a_relative_symlink_to_the_run_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root, START)
    assert layout.run is not None and layout.commit_latest() == ()
    link = root / "out" / "orders" / "current"
    assert link.is_symlink()
    assert os.readlink(link) == layout.run.run_id


def test_an_older_run_finishing_last_does_not_move_latest_back(tmp_path: Path) -> None:
    root = _project(tmp_path)
    older, newer = _open(root, START), _open(root, START + timedelta(seconds=1))
    assert older.run is not None and newer.run is not None
    newer.commit_latest()
    older.commit_latest()
    held = (root / "out" / "orders" / "LATEST").read_text(encoding="utf-8").strip()
    assert held == newer.run.run_id


def test_a_failed_run_leaves_latest_and_an_empty_run_folder_is_removed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    assert _run(cfg).exit_code == 0
    (kept,) = _runs(root, "orders")
    (root / "a.csv").unlink()
    assert _run(cfg).exit_code != 0
    assert _runs(root, "orders") == [kept]
    assert (root / "out" / "orders" / "LATEST").read_text(encoding="utf-8").strip() == kept.name


def test_a_runtime_failure_after_a_write_keeps_the_folder_and_leaves_latest(
    tmp_path: Path, monkeypatch
) -> None:
    from decoy.cli.io import _targets

    root = _project(tmp_path)
    cfg_dict = _config(root)
    cfg_dict["sources"]["b"] = csv_source(root / "a.csv")
    cfg_dict["tables"].append({"name": "b", "columns": [{"name": "email", "strategy": "redact"}]})
    cfg_dict["targets"]["b"] = {"type": "file", "format": "csv", "path": "b.csv"}
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    real, calls = _targets.write_table, []

    def second_fails(table, fmt, path, layout=None):
        calls.append(path.name)
        if len(calls) == 2:
            raise OSError(5, "boom")
        real(table, fmt, path, layout)

    monkeypatch.setattr(_targets, "write_table", second_fails)
    result = _run(cfg)
    assert result.exit_code == 3, result.output
    (run,) = _runs(root, "orders")
    assert any(run.iterdir())
    assert not (root / "out" / "orders" / "LATEST").exists()


def test_an_interrupt_after_a_write_keeps_the_folder_and_leaves_latest(
    tmp_path: Path, monkeypatch
) -> None:
    from decoy.cli.io import _targets

    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    real = _targets.write_table

    def write_then_interrupt(table, fmt, path, layout=None):
        real(table, fmt, path, layout)
        raise KeyboardInterrupt

    monkeypatch.setattr(_targets, "write_table", write_then_interrupt)
    result = _run(cfg)
    assert result.exit_code != 0, result.output
    (run,) = _runs(root, "orders")
    assert (run / "masked.csv").is_file()
    assert not (root / "out" / "orders" / "LATEST").exists()


@posix_only
def test_a_file_named_current_gives_a_warning_and_exit_zero(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    (root / "out" / "orders").mkdir(parents=True)
    (root / "out" / "orders" / "current").write_text("mine", encoding="utf-8")
    result = _run(cfg)
    assert result.exit_code == 0, result.output
    assert "layout.latest_link_failed" in result.output
    assert (root / "out" / "orders" / "current").read_text(encoding="utf-8") == "mine"


def test_abandon_removes_empty_nested_folders_and_keeps_written_files(tmp_path: Path) -> None:
    root = _project(tmp_path)
    empty, written = _open(root, START), _open(root, START + timedelta(seconds=1))
    assert empty.run is not None and written.run is not None
    (empty.run.path / "a" / "b").mkdir(parents=True)
    (written.run.path / "a" / "b").mkdir(parents=True)
    (written.run.path / "a" / "b" / "t.csv").write_text("x\n", encoding="utf-8")
    (written.run.path / "c").mkdir()
    empty.abandon()
    written.abandon()
    assert not empty.run.path.exists()
    assert (written.run.path / "a" / "b" / "t.csv").is_file()
    assert not (written.run.path / "c").exists()


def test_an_invalid_latest_warns_and_the_next_clean_run_repairs_it(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root, START)
    (root / "out" / "orders" / "LATEST").write_text("garbage\n", encoding="utf-8")
    warnings = layout.commit_latest()
    assert [w.code for w in warnings] == ["layout.latest_invalid"]
    assert layout.run is not None
    held = (root / "out" / "orders" / "LATEST").read_text(encoding="utf-8").strip()
    assert held == layout.run.run_id


def _commit_within(layout: RunLayout, latest: Path, seconds: float = 10) -> tuple:
    """`commit_latest()` on a thread, so a read that blocks fails the test instead of hanging."""
    result: list[tuple] = []
    thread = threading.Thread(target=lambda: result.append(layout.commit_latest()), daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive() and latest.is_fifo():
        # Release a reader stuck on the pipe so the test run itself does not hang.
        os.close(os.open(latest, os.O_WRONLY | getattr(os, "O_NONBLOCK", 0)))
    assert not thread.is_alive() and result, "commit_latest blocked reading LATEST"
    return result[0]


# The flags Windows lacks. Removing them must not open a hole: the reader checks with lstat first.
_PLATFORM_FLAGS = ("O_NOFOLLOW", "O_NONBLOCK", "O_NOCTTY")


def _drop_flags(monkeypatch: pytest.MonkeyPatch, gap: bool) -> None:
    if gap:
        for name in _PLATFORM_FLAGS:
            monkeypatch.delattr(os, name, raising=False)


def _plant_latest(kind: str, latest: Path, later_id: str, scratch: Path) -> Path | None:
    """Put a non-regular `LATEST` in place; returns the link target a run must not touch."""
    if kind == "fifo":
        os.mkfifo(latest)
        return None
    if kind == "device link":
        os.symlink("/dev/zero", latest)
        return None
    # The target names a later run, so reading through the link would hold LATEST back.
    target = scratch / "victim.txt"
    target.write_text(f"{later_id}\n", encoding="utf-8")
    os.symlink(target, latest)
    return target


@posix_only
@pytest.mark.parametrize("gap", [False, True], ids=["all flags", "no O_NOFOLLOW"])
@pytest.mark.parametrize("kind", ["fifo", "link to a later run id", "device link"])
def test_a_latest_that_is_not_a_regular_file_is_warned_and_replaced(
    tmp_path: Path, kind: str, gap: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A device node needs root to make, so a link to /dev/zero stands in for it."""
    root = _project(tmp_path)
    layout, later = _open(root, START), _open(root, START + timedelta(days=1))
    assert layout.run is not None and later.run is not None
    latest = root / "out" / "orders" / "LATEST"
    target = _plant_latest(kind, latest, later.run.run_id, tmp_path)
    _drop_flags(monkeypatch, gap)
    warnings = _commit_within(layout, latest)
    assert [w.code for w in warnings] == ["layout.latest_invalid"]
    assert latest.is_file() and not latest.is_symlink()
    assert latest.read_text(encoding="utf-8").strip() == layout.run.run_id
    if target is not None:
        assert target.read_text(encoding="utf-8") == f"{later.run.run_id}\n"


@posix_only
def test_a_planted_current_symlink_is_replaced_and_its_target_unchanged(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = _open(root, START)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    link = root / "out" / "orders" / "current"
    os.symlink(victim, link)
    layout.commit_latest()
    assert layout.run is not None
    assert os.readlink(link) == layout.run.run_id
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep"


# --- AT-7 claim ---------------------------------------------------------------------------


def test_the_first_run_writes_the_claim_for_a_pipelines_member_and_a_free_yaml(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    member = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    free = _write(root, "jobs/members.yaml", _config(root))
    assert _run(member).exit_code == 0 and _run(free).exit_code == 0
    claim = root / "out" / "orders" / "PIPELINE"
    assert claim.read_text(encoding="utf-8").strip() == "pipelines/orders/pipeline.yaml"
    other = root / "out" / "members" / "PIPELINE"
    assert other.read_text(encoding="utf-8").strip() == "jobs/members.yaml"


def test_a_second_yaml_declaring_a_claimed_name_exits_1_before_any_write(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = _write(root, "jobs/a.yaml", _config(root, name="orders"))
    second = _write(root, "old/b.yaml", _config(root, name="orders"))
    assert _run(first).exit_code == 0
    before = _runs(root, "orders")
    result = _run(second)
    assert result.exit_code == 1, result.output
    assert "layout.pipeline_name_collision" in result.output
    assert _runs(root, "orders") == before


def test_a_second_yaml_deriving_a_claimed_name_gets_a_hash_suffix(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = _write(root, "jobs/orders.yaml", _config(root))
    second = _write(root, "old/orders.yaml", _config(root))
    assert _run(first).exit_code == 0 and _run(second).exit_code == 0
    derived = [p.name for p in (root / "out").iterdir() if p.name.startswith("orders-")]
    assert len(derived) == 1 and re.fullmatch(r"orders-[0-9a-f]{6}", derived[0])


def test_a_pipelines_folder_name_is_taken_even_before_its_first_run(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pipelines" / "orders").mkdir(parents=True)
    undeclared = _write(root, "jobs/orders.yaml", _config(root))
    assert _run(undeclared).exit_code == 0
    assert not (root / "out" / "orders").exists()
    assert any(p.name.startswith("orders-") for p in (root / "out").iterdir())
    declared = _write(root, "jobs/other.yaml", _config(root, name="orders"))
    result = _run(declared)
    assert result.exit_code == 1 and "layout.pipeline_name_collision" in result.output


def test_a_pipelines_run_that_finds_another_yamls_claim_exits_1(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = _write(root, "jobs/orders.yaml", _config(root, name="orders"))
    assert _run(first).exit_code == 0
    member = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    result = _run(member)
    assert result.exit_code == 1, result.output
    assert "layout.pipeline_name_collision" in result.output


def test_two_racing_first_runs_leave_one_claim_and_no_temp_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    barrier = threading.Barrier(2)
    layouts: list[RunLayout] = []
    errors: list[BaseException] = []

    def go() -> None:
        try:
            barrier.wait()
            layouts.append(_open(root))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(layouts) == 2
    folder = root / "out" / "orders"
    assert (folder / "PIPELINE").read_text(encoding="utf-8").strip() == ORDERS.yaml_rel
    assert [p.name for p in folder.iterdir() if p.name.startswith(".")] == []


def test_a_mount_without_hard_links_exits_3(tmp_path: Path, monkeypatch) -> None:
    from decoy import _atomic

    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))

    def no_links(*_a, **_k):
        raise _atomic.AtomicWriteError(_atomic.ATOMIC_NOCLOBBER_UNSUPPORTED, None)

    monkeypatch.setattr("decoy.cli.io._layout.write_atomic", no_links)
    result = _run(cfg)
    assert result.exit_code == 3, result.output


def test_a_config_with_only_absolute_targets_writes_no_claim_and_no_out(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg_dict = _config(root)
    cfg_dict["targets"]["a"]["path"] = str(tmp_path / "abs.csv")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    assert _run(cfg).exit_code == 0
    assert not (root / "out").exists()


# --- AT-10 config untouched, quarantine ---------------------------------------------------


def _quarantine_config(root: Path) -> dict:
    return _config(
        root,
        quarantine={"enabled": True, "output_path": "q.jsonl", "triggers": ["format_error"]},
    )


def _spy_run_pipeline(monkeypatch) -> list[dict]:
    import decoy_engine

    seen: list[dict] = []
    real = decoy_engine.run_pipeline

    def spy(config, *a, **k):
        seen.append({"config": copy.deepcopy(config), **k})
        return real(config, *a, **k)

    monkeypatch.setattr(decoy_engine, "run_pipeline", spy)
    return seen


def test_quarantine_goes_to_the_engine_as_the_placed_path_not_in_the_config(
    tmp_path: Path, monkeypatch
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _quarantine_config(root))
    seen = _spy_run_pipeline(monkeypatch)
    result = _run(cfg)
    assert result.exit_code == 0, result.output
    (run,) = _runs(root, "orders")
    (call,) = seen
    assert call["quarantine_path"] == str(run.resolve() / "q.jsonl")
    assert call["config"]["quarantine"]["output_path"] == "q.jsonl"


def test_an_absolute_quarantine_path_is_honored(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg_dict = _quarantine_config(root)
    cfg_dict["quarantine"]["output_path"] = str(tmp_path / "abs-q.jsonl")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    seen = _spy_run_pipeline(monkeypatch)
    assert _run(cfg).exit_code == 0
    assert seen[0]["quarantine_path"] == str(tmp_path / "abs-q.jsonl")


def test_a_config_without_quarantine_passes_no_quarantine_path(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    seen = _spy_run_pipeline(monkeypatch)
    assert _run(cfg).exit_code == 0
    assert "quarantine_path" not in seen[0]


def test_the_yaml_file_is_untouched_by_a_run(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _quarantine_config(root))
    before = cfg.read_bytes()
    assert _run(cfg).exit_code == 0
    assert cfg.read_bytes() == before


def test_mask_passes_the_quarantine_path_placed_against_its_base(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "proj"
    cfg = _write(root, "pipeline.yaml", _quarantine_config(root))
    seen = _spy_run_pipeline(monkeypatch)
    decoy.mask(config=str(cfg))
    assert seen[0]["quarantine_path"] == str((root / "q.jsonl").resolve())


def test_the_engine_gets_the_loaded_config_unchanged_and_one_hash_across_runs(
    tmp_path: Path, monkeypatch
) -> None:
    from decoy_engine import pipeline_config_hash

    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _quarantine_config(root))
    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    seen = _spy_run_pipeline(monkeypatch)
    assert _run(cfg).exit_code == 0 and _run(cfg).exit_code == 0
    first, second = seen
    assert first["quarantine_path"] != second["quarantine_path"]
    assert first["config"]["quarantine"] == loaded["quarantine"]
    assert pipeline_config_hash(first["config"]) == pipeline_config_hash(second["config"])


def test_tokenize_places_its_quarantine_path_in_the_run_folder(tmp_path: Path, monkeypatch) -> None:
    from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    root = _project(tmp_path)
    cfg_dict = _quarantine_config(root)
    cfg_dict["global_settings"]["mask_secret_ref"] = TEST_MASK_SECRET_REF
    cfg_dict["tables"][0]["columns"][0] = {
        "name": "email",
        "strategy": "tokenize",
        "namespace": "em",
    }
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    seen = _spy_run_pipeline(monkeypatch)
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")])
    assert result.exit_code == 0, result.output
    (run,) = _runs(root, "orders")
    assert seen[0]["quarantine_path"] == str(run.resolve() / "q.jsonl")
    assert seen[0]["config"]["quarantine"]["output_path"] == "q.jsonl"
