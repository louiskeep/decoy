"""`decoy library prune` and `decoy library clean` (plan 4.7, 4.8, 4.15; L4b).

Both resolve the exact targets read-only first and print them; nothing is deleted without
`--yes`. Neither touches anything outside the library's records (prune) or `scratch/` (clean):
no vault file, key, target, `out/` run folder or file outside the library root.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from decoy_engine import records
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RUNTIME
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import _fsck, open_library
from tests.unit.library._helpers import (
    INVOCATION,
    PRODUCER,
    envelope,
    object_files,
    object_path,
    start_child,
)

runner = CliRunner()
OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    return tmp_path / DECOY_DIR


def _cli(root: Path, *args: str) -> Any:
    return runner.invoke(app, ["library", *args, "--library", str(root)])


def _rec(n: int, at: datetime) -> records.RecordEnvelope:
    payload = json.loads(records.encode(envelope(n)))["payload"]
    return records.build(
        "sample-run", payload, producer=PRODUCER, invocation_id=INVOCATION, created_at=at
    )


def _put_old(root: Path, count: int) -> list[str]:
    library = open_library(root)
    return [library.put(_rec(n, OLD + timedelta(days=n))).id for n in range(count)]


# -- prune -------------------------------------------------------------------------------------


def test_prune_previews_exact_ids_then_deletes_with_yes(root: Path) -> None:
    ids = _put_old(root, 3)
    preview = _cli(root, "prune", "--keep-last", "1")
    assert preview.exit_code == EXIT_OK, preview.output
    assert all(i in preview.output for i in ids[:2]) and ids[2] not in preview.output
    assert len(object_files(root)) == 3  # nothing deleted without --yes
    applied = _cli(root, "prune", "--keep-last", "1", "--yes")
    assert applied.exit_code == EXIT_OK, applied.output
    assert [p.name for p in object_files(root)] == [object_path(root, ids[2]).name]


def test_prune_with_no_arguments_applies_the_policy_or_keeps_all(root: Path) -> None:
    ids = _put_old(root, 3)
    keep_all = _cli(root, "prune", "--yes")
    assert keep_all.exit_code == EXIT_OK and len(object_files(root)) == 3
    (root / "library.yaml").write_text(
        "retention:\n  records:\n    default: {keep_last: 2}\n", encoding="utf-8"
    )
    preview = _cli(root, "prune")
    assert ids[0] in preview.output and len(object_files(root)) == 3
    assert _cli(root, "prune", "--yes").exit_code == EXIT_OK
    assert len(object_files(root)) == 2


@pytest.mark.parametrize(
    "args", [("--keep-last", "-1"), ("--older-than", "soon"), ("--older-than", "3w")]
)
def test_prune_refuses_bad_arguments(root: Path, args: tuple[str, ...]) -> None:
    _put_old(root, 1)
    result = _cli(root, "prune", *args)
    assert result.exit_code != EXIT_OK and len(object_files(root)) == 1


def test_prune_refuses_in_degraded_mode(root: Path) -> None:
    _put_old(root, 2)
    (root / "library" / "index.sqlite").unlink()
    (root / "library" / "index.sqlite").mkdir()
    result = _cli(root, "prune", "--keep-last", "0", "--yes")
    assert result.exit_code == EXIT_RUNTIME
    assert "library_lock_unavailable" in result.output
    assert len(object_files(root)) == 2


_HOLD_LOCK = (
    "import sqlite3, sys, time\n"
    "from pathlib import Path\n"
    "conn = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
    "conn.execute('BEGIN IMMEDIATE')\n"
    "print('held', flush=True)\n"
    "while not Path(sys.argv[2]).exists():\n"
    "    time.sleep(0.01)\n"
    "conn.execute('ROLLBACK')\n"
)


def test_prune_waits_for_the_lock_and_deletes_nothing_while_it_is_held(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ML4-unlocked: pruning without the library lock deletes while another holds it; red."""
    from decoy.cli.library import _index

    _put_old(root, 3)
    monkeypatch.setattr(_index, "BUSY_TIMEOUT_SECONDS", 0.3)
    release = tmp_path / "release"
    holder = start_child(_HOLD_LOCK, str(root / "library" / "index.sqlite"), str(release))
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        from decoy.cli.library import _prune

        library = open_library(root)  # opening degrades nothing: the lock is only busy
        with pytest.raises(Exception) as caught:
            _prune.prune_apply(library, [_prune.Rule(keep_last=0)], now=datetime.now(timezone.utc))
        assert getattr(caught.value, "code", None) == "library_busy"
        assert len(object_files(root)) == 3
    finally:
        release.touch()
        holder.wait(timeout=10)


_PUT_LOOP = (
    "import sys\n"
    "from datetime import datetime, timezone\n"
    "from pathlib import Path\n"
    "from decoy_engine import records\n"
    "from tests.unit.library._helpers import INVOCATION, PRODUCER, envelope\n"
    "from decoy.cli.library import open_library\n"
    "import json\n"
    "library = open_library(Path(sys.argv[1]))\n"
    "for n in range(100, 140):\n"
    "    payload = json.loads(records.encode(envelope(n)))['payload']\n"
    "    env = records.build('sample-run', payload, producer=PRODUCER, invocation_id=INVOCATION,\n"
    "                        created_at=datetime.now(timezone.utc))\n"
    "    print(library.put(env).id, flush=True)\n"
)


def test_prune_while_another_process_puts(root: Path) -> None:
    old = _put_old(root, 10)
    child = start_child(_PUT_LOOP, str(root))
    result = _cli(root, "prune", "--keep-last", "0", "--yes")
    out, err = child.communicate(timeout=180)
    assert child.returncode == 0, err
    assert result.exit_code == EXIT_OK, result.output
    new_ids = out.split()
    assert len(new_ids) == 40  # non-vacuous: the other process really wrote
    names = {p.name for p in object_files(root)}
    assert all(object_path(root, i).name in names for i in new_ids)  # none of them deleted
    assert not any(object_path(root, i).name in names for i in old)
    open_library(root)  # the next open catches the index up
    report = _fsck.check(root)
    assert report.clean, report.items


# -- clean -------------------------------------------------------------------------------------


def _scratch(root: Path) -> Path:
    library = open_library(root)
    with library.scratch("sample", INVOCATION, ttl=timedelta(hours=1)) as alloc:
        alloc.write("orders.csv", b"rows")
        alloc.write("users.csv", b"rows")
    return alloc.path


def test_clean_previews_then_removes_only_scratch(root: Path, tmp_path: Path) -> None:
    """ML4-wide: removing `.decoy/` instead of `scratch/` turns this red."""
    ids = _put_old(root, 1)
    alloc = _scratch(root)
    vault = tmp_path / "vault.db"
    vault.write_bytes(b"the vault")
    key = tmp_path / "keys" / "mask.key"
    key.parent.mkdir()
    key.write_bytes(b"key")
    preview = _cli(root, "clean")
    assert preview.exit_code == EXIT_OK, preview.output
    assert alloc.name in preview.output and alloc.exists()  # previewed, not removed
    applied = _cli(root, "clean", "--yes")
    assert applied.exit_code == EXIT_OK, applied.output
    assert not alloc.exists() and (root / "scratch").is_dir()
    assert vault.read_bytes() == b"the vault" and key.read_bytes() == b"key"
    assert [p.name for p in object_files(root)] == [object_path(root, ids[0]).name]
    assert (root / ".gitignore").exists() and (root / "library" / "LAYOUT").exists()


def test_clean_lists_a_held_file_and_exits_4(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux run of L4b-clean-open with the PermissionError forced (ML4-clean-raise)."""
    alloc = _scratch(root)
    real = os.unlink

    def unlink(path: object, *a: object, **k: object) -> None:
        if os.fspath(path).endswith("orders.csv"):  # type: ignore[arg-type]
            raise PermissionError(13, "held open")
        real(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", unlink)
    result = _cli(root, "clean", "--yes")
    monkeypatch.undo()
    assert result.exit_code == EXIT_FINDINGS, result.output
    assert "orders.csv" in result.output  # listed as left behind
    assert (alloc / "orders.csv").exists() and not (alloc / "users.csv").exists()


def test_clean_with_no_scratch_is_a_no_op(root: Path) -> None:
    _put_old(root, 1)
    result = _cli(root, "clean", "--yes")
    assert result.exit_code == EXIT_OK and len(object_files(root)) == 1


def test_clean_refuses_in_degraded_mode(root: Path) -> None:
    alloc = _scratch(root)
    (root / "library" / "index.sqlite").unlink(missing_ok=True)
    (root / "library" / "index.sqlite").mkdir()
    result = _cli(root, "clean", "--yes")
    assert result.exit_code == EXIT_RUNTIME and alloc.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows lane: a held-open file blocks delete")
def test_clean_with_a_file_held_open_on_windows(root: Path) -> None:
    alloc = _scratch(root)
    with (alloc / "orders.csv").open("rb"):
        result = _cli(root, "clean", "--yes")
    assert result.exit_code == EXIT_FINDINGS and "orders.csv" in result.output
    assert not (alloc / "users.csv").exists()
