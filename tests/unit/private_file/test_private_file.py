"""`_private_file`: owner-only creation and the one mode call (X7c slice S1)."""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from tests.csv_sources import csv_source

from decoy import _private_file
from decoy._private_file import (
    PRIVATE_EXISTS,
    PRIVATE_MODE_FAILED,
    PRIVATE_OPEN_FAILED,
    PrivateFileError,
    apply_mode,
    create_exclusive,
    create_private_directory,
    create_private_temp,
    open_private,
    restrict_owner_only,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes and symlinks")


def _mode(p: Path | str) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


def _run(code: str, *argv: str) -> str:
    """Run `code` in a child so the umask never touches the pytest worker."""
    done = subprocess.run(
        [sys.executable, "-c", code, *argv], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


# -- AT-P1a: owner-only before the first byte ----------------------------------------------

_BEFORE_FIRST_BYTE = (
    "import os, stat, sys\n"
    "from pathlib import Path\n"
    "from decoy._atomic import staged_private_target\n"
    "os.umask(0)\n"
    "with staged_private_target(Path(sys.argv[1])) as tmp:\n"
    "    print(oct(stat.S_IMODE(os.stat(tmp).st_mode)), os.stat(tmp).st_size)\n"
    "    tmp.write_bytes(b'x')\n"
)

_PUBLISHED = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from decoy._atomic import WriteMode, write_local_target\n"
    "os.umask(0)\n"
    "write_local_target(Path(sys.argv[1]), b'x', WriteMode.REPLACE)\n"
)


@posix_only
def test_the_private_stage_is_0600_before_any_byte_under_umask_000(tmp_path: Path) -> None:
    seen = _run(_BEFORE_FIRST_BYTE, str(tmp_path / "out.csv"))
    assert seen == "0o600 0"


@posix_only
def test_write_local_target_publishes_0600_under_umask_000(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    _run(_PUBLISHED, str(target))
    assert target.read_bytes() == b"x"
    assert _mode(target) == 0o600


# -- AT-P1b: create_private_temp and open_private -------------------------------------------

_SPOOL = (
    "import os, stat\n"
    "from decoy._private_file import create_private_temp\n"
    "os.umask(0)\n"
    "p = create_private_temp('decoy-mask-t-')\n"
    "print(oct(stat.S_IMODE(os.stat(p).st_mode)), p.name.startswith('.decoy-mask-t-'),"
    " p.name.endswith('.tmp'))\n"
    "os.unlink(p)\n"
)

_OPEN = (
    "import os, stat, sys\n"
    "from pathlib import Path\n"
    "from decoy._private_file import open_private\n"
    "os.umask(0)\n"
    "parent = Path(sys.argv[1]) / 'vaults'\n"
    "parent.mkdir()\n"
    "open_private(parent / 'v.db', new_parent=True)\n"
    "print(oct(stat.S_IMODE(os.stat(parent / 'v.db').st_mode)),"
    " oct(stat.S_IMODE(os.stat(parent).st_mode)))\n"
)


@posix_only
def test_create_private_temp_is_0600_under_umask_000() -> None:
    assert _run(_SPOOL) == "0o600 True True"


@posix_only
def test_open_private_creates_0600_and_narrows_a_new_parent(tmp_path: Path) -> None:
    assert _run(_OPEN, str(tmp_path)) == "0o600 0o700"


@posix_only
def test_open_private_repairs_a_file_an_earlier_build_left_wide(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    path.write_bytes(b"keep")
    path.chmod(0o644)
    open_private(path, new_parent=False)
    assert _mode(path) == 0o600 and path.read_bytes() == b"keep"


@posix_only
def test_open_private_leaves_an_existing_parent_alone(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    open_private(tmp_path / "v.db", new_parent=False)
    assert _mode(tmp_path) == 0o755


# -- AT-P1c: planted names ------------------------------------------------------------------


@posix_only
def test_a_symlink_at_the_open_private_path_is_refused(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"mine")
    victim.chmod(0o644)
    link = tmp_path / "v.db"
    link.symlink_to(victim)
    with pytest.raises(PrivateFileError) as caught:
        open_private(link, new_parent=False)
    assert caught.value.code == PRIVATE_OPEN_FAILED
    assert caught.value.errno == errno.ELOOP
    assert victim.read_bytes() == b"mine" and _mode(victim) == 0o644


@posix_only
@pytest.mark.parametrize("planted", ["symlink", "file"])
def test_a_planted_staging_name_is_a_collision_and_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, planted: str
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"mine")
    victim.chmod(0o644)
    clash = tmp_path / ".out.csv.decoy-aaaa.tmp"
    if planted == "symlink":
        clash.symlink_to(victim)
    else:
        clash.write_bytes(b"other")
    names = iter(["aaaa", "bbbb"])
    monkeypatch.setattr(_private_file.secrets, "token_hex", lambda _n: next(names))
    tmp, _bits = create_exclusive(tmp_path, "out.csv", private=True)
    assert Path(tmp).name == ".out.csv.decoy-bbbb.tmp" and _mode(tmp) == 0o600
    assert victim.read_bytes() == b"mine" and _mode(victim) == 0o644
    assert clash.is_symlink() == (planted == "symlink")


# -- AT-P1e: the mode check and the Windows branch ------------------------------------------


@posix_only
def test_restrict_owner_only_leaves_no_group_or_other_bit(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"")
    path.chmod(0o666)
    fd = os.open(path, os.O_RDWR)
    try:
        restrict_owner_only(fd, str(path))
    finally:
        os.close(fd)
    assert _mode(path) == 0o600


@posix_only
def test_restrict_owner_only_raises_eperm_when_the_mode_does_not_stick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"")
    path.chmod(0o644)
    monkeypatch.setattr(os, "fchmod", lambda *_a: None)
    fd = os.open(path, os.O_RDWR)
    try:
        with pytest.raises(OSError) as caught:
            restrict_owner_only(fd, str(path))
    finally:
        os.close(fd)
    assert not isinstance(caught.value, PrivateFileError)
    assert caught.value.errno == errno.EPERM


def test_on_windows_the_mode_goes_by_path_and_is_not_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(_private_file, "_WINDOWS", True)
    monkeypatch.setattr(os, "chmod", lambda p, bits: calls.append((str(p), bits)))
    # fd -1 makes any fchmod or fstat raise EBADF, so a pass shows neither is used.
    restrict_owner_only(-1, str(tmp_path / "f"))
    apply_mode(-1, str(tmp_path / "d"), 0o700)
    assert calls == [(str(tmp_path / "f"), 0o600), (str(tmp_path / "d"), 0o700)]


# -- AT-P1f: narrowing follows the opened inode, not the name -------------------------------


@posix_only
def test_a_path_swapped_after_the_open_keeps_its_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "v.db"
    swapped = tmp_path / "other.db"
    swapped.write_bytes(b"other")
    swapped.chmod(0o644)
    real_open = os.open
    fired: list[bool] = []

    def swap_after_open(p, flags, *a, **k):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **k)
        if Path(p) == path and not fired:
            fired.append(True)
            os.rename(swapped, path)
        return fd

    monkeypatch.setattr(_private_file.os, "open", swap_after_open)
    open_private(path, new_parent=False)
    monkeypatch.undo()
    assert fired and path.read_bytes() == b"other"
    assert _mode(path) == 0o644


# -- errors carry a code and an errno, never a path -----------------------------------------


@posix_only
def test_a_failed_open_is_a_value_free_private_error(tmp_path: Path) -> None:
    missing = tmp_path / "secret-dir" / "v.db"
    with pytest.raises(PrivateFileError) as caught:
        open_private(missing, new_parent=False)
    exc = caught.value
    assert exc.code == PRIVATE_OPEN_FAILED and exc.errno == errno.ENOENT
    assert str(exc) == exc.code and exc.filename is None
    assert exc.__cause__ is None and exc.__context__ is None


@posix_only
def test_a_narrowing_failure_is_a_value_free_private_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object) -> None:
        raise OSError(errno.EIO, "no", "/secret/path")

    monkeypatch.setattr(os, "fchmod", boom)
    with pytest.raises(PrivateFileError) as caught:
        open_private(tmp_path / "v.db", new_parent=False)
    exc = caught.value
    assert exc.code == PRIVATE_MODE_FAILED and exc.errno == errno.EIO
    assert "secret" not in str(exc) and exc.__context__ is None


@posix_only
def test_create_private_temp_failures_map_to_the_two_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_private_file.tempfile, "gettempdir", lambda: str(tmp_path / "gone"))
    with pytest.raises(PrivateFileError) as caught:
        create_private_temp("decoy-mask-t-")
    assert caught.value.code == PRIVATE_OPEN_FAILED
    monkeypatch.setattr(_private_file.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*_a: object) -> None:
        raise OSError(errno.EIO, "no")

    monkeypatch.setattr(os, "fchmod", boom)
    with pytest.raises(PrivateFileError) as caught2:
        create_private_temp("decoy-mask-t-")
    assert caught2.value.code == PRIVATE_MODE_FAILED
    assert sorted(p.name for p in tmp_path.iterdir()) == []  # the half-made temp is removed


@posix_only
def test_installer_trust_state_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    """The recorder publishes through `write_atomic`, which is private whatever the umask."""
    code = (
        "import os, sys; os.umask(0)\n"
        "from pathlib import Path\n"
        "from decoy.distribution import installer\n"
        "from decoy.distribution import version_document as vd\n"
        "doc = vd.build_document(latest='0.1.0', min_supported='0.1.0', artifacts={}, serial=1)\n"
        "installer.check_document_freshness(doc, Path(sys.argv[1]))\n"
    )
    _run(code, str(tmp_path))
    assert _mode(tmp_path / "trust_state.json") == 0o600


def test_a_failed_spool_write_removes_the_registered_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pandas as pd
    import pyarrow.parquet as pq

    import decoy

    monkeypatch.setattr(_private_file.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*_a: object, **_k: object) -> None:
        raise OSError(errno.EIO, "disk says no")

    monkeypatch.setattr(pq, "write_table", boom)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "sources": {"t": csv_source("unused.csv")},
        "tables": [{"name": "t", "columns": [{"name": "a", "strategy": "passthrough"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}},
    }
    with pytest.raises(OSError):
        decoy.mask(pd.DataFrame({"a": [1]}), cfg)
    assert sorted(p.name for p in tmp_path.iterdir()) == []


# -- create_private_directory: the run-folder creator -----------------------------------------

_DIRECTORY = (
    "import os, stat, sys\n"
    "from pathlib import Path\n"
    "from decoy._private_file import create_private_directory\n"
    "os.umask(0)\n"
    "create_private_directory(Path(sys.argv[1]) / 'run')\n"
    "print(oct(stat.S_IMODE(os.stat(Path(sys.argv[1]) / 'run').st_mode)))\n"
)


@posix_only
def test_create_private_directory_is_0700_under_umask_000(tmp_path: Path) -> None:
    assert _run(_DIRECTORY, str(tmp_path)) == "0o700"


@posix_only
def test_create_private_directory_is_0700_under_a_restrictive_umask(tmp_path: Path) -> None:
    old = os.umask(0o777)
    try:
        create_private_directory(tmp_path / "run")
    finally:
        os.umask(old)
    assert _mode(tmp_path / "run") == 0o700


@posix_only
def test_an_existing_entry_is_private_exists_and_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "keep").write_bytes(b"x")
    with pytest.raises(PrivateFileError) as caught:
        create_private_directory(tmp_path / "run")
    assert caught.value.code == PRIVATE_EXISTS
    assert (tmp_path / "run" / "keep").read_bytes() == b"x"


@posix_only
def test_a_symlink_at_the_directory_path_is_exists_and_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    target.chmod(0o755)
    (tmp_path / "run").symlink_to(target)
    with pytest.raises(PrivateFileError) as caught:
        create_private_directory(tmp_path / "run")
    assert caught.value.code == PRIVATE_EXISTS
    assert _mode(target) == 0o755


def test_a_missing_parent_is_an_open_failure(tmp_path: Path) -> None:
    with pytest.raises(PrivateFileError) as caught:
        create_private_directory(tmp_path / "gone" / "run")
    assert caught.value.code == PRIVATE_OPEN_FAILED
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@posix_only
def test_a_mode_that_does_not_stick_removes_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object) -> None:
        raise OSError(errno.EIO, "no")

    monkeypatch.setattr(os, "fchmod", boom)
    with pytest.raises(PrivateFileError) as caught:
        create_private_directory(tmp_path / "run")
    assert caught.value.code == PRIVATE_MODE_FAILED
    assert not (tmp_path / "run").exists()


@posix_only
def test_a_mount_that_ignores_chmod_is_refused_by_the_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "fchmod", lambda *_a: None)
    real_mkdir = os.mkdir
    old = os.umask(0)
    try:
        monkeypatch.setattr(os, "mkdir", lambda p, mode=0o777: real_mkdir(p, 0o755))
        with pytest.raises(PrivateFileError) as caught:
            create_private_directory(tmp_path / "run")
    finally:
        os.umask(old)
    assert caught.value.code == PRIVATE_MODE_FAILED
    assert not (tmp_path / "run").exists()


_LAYOUT_FILES = (
    "import os, stat, sys\n"
    "from pathlib import Path\n"
    "from decoy.cli.io import (\n"
    "    PipelineName, RunLayout, ensure_decoy_dir, name_dir, prepare_out, write_claim,\n"
    ")\n"
    "os.umask(0)\n"
    "root = Path(sys.argv[1])\n"
    "out, _ = prepare_out(root)\n"
    "ensure_decoy_dir(root)\n"
    "write_claim(name_dir(out, 'p'), 'jobs/p.yaml')\n"
    "name = PipelineName('p', False, 'jobs/p.yaml')\n"
    "assert RunLayout.open(root, name, '0a1b2c3d-0000-4000-8000-000000000000').commit_latest() == ()\n"
    "for rel in ('out/.gitignore', '.decoy/.gitignore', 'out/p/PIPELINE', 'out/p/LATEST'):\n"
    "    print(rel, oct(stat.S_IMODE(os.stat(root / rel).st_mode)))\n"
)


@posix_only
def test_layout_files_are_owner_only_under_umask_zero(tmp_path: Path) -> None:
    """`out/.gitignore`, `.decoy/.gitignore`, the claim and `LATEST` go through the atomic writer."""
    got = _run(_LAYOUT_FILES, str(tmp_path)).splitlines()
    assert got == [
        "out/.gitignore 0o600",
        ".decoy/.gitignore 0o600",
        "out/p/PIPELINE 0o600",
        "out/p/LATEST 0o600",
    ]


_LIBRARY_FILES = (
    "import os, stat, sys\n"
    "from datetime import datetime, timezone\n"
    "from pathlib import Path\n"
    "from decoy_engine import records\n"
    "from decoy.cli.io import DECOY_DIR\n"
    "from decoy.cli.library import open_library\n"
    "os.umask(0)\n"
    "root = Path(sys.argv[1]) / DECOY_DIR\n"
    "payload = {'sample_size': 1, 'root_table': 't', 'table_rows': {'t': 1},\n"
    "    'subset_seed_counts': {'t': 1}, 'approximate_columns': (), 'scratch_dir': 's',\n"
    "    'outputs': (), 'ttl_seconds': 60}\n"
    "env = records.build('sample-run', payload,\n"
    "    producer={'name': 'decoy-cli', 'version': '0.0.0', 'engine_version': '0.22.0'},\n"
    "    invocation_id='0b6c9a3e-1d2f-4c5b-8a7e-9f0e1d2c3b4a',\n"
    "    created_at=datetime(2026, 11, 11, tzinfo=timezone.utc))\n"
    "open_library(root).put(env)\n"
    "for p in sorted(root.rglob('*')):\n"
    "    kind = 'dir' if p.is_dir() else 'file'\n"
    "    print(kind, oct(stat.S_IMODE(os.stat(p).st_mode)))\n"
    "print('root', oct(stat.S_IMODE(os.stat(root).st_mode)))\n"
)


@posix_only
def test_library_files_and_folders_are_owner_only_under_umask_zero(tmp_path: Path) -> None:
    """Library folders come from `create_private_directory`; records, `LAYOUT` and the git files
    from the atomic writer."""
    got = _run(_LIBRARY_FILES, str(tmp_path)).splitlines()
    files = [line for line in got if line.startswith("file ")]
    dirs = [line for line in got if line.startswith(("dir ", "root "))]
    assert len(files) == 5  # .gitignore, .gitattributes, LAYOUT, index.sqlite, one record
    assert set(files) == {"file 0o600"}
    assert len(dirs) == 5  # the root, library, objects, the fan-out folder, tmp
    assert {line.split()[1] for line in dirs} == {"0o700"}


_LIBRARY_LOCK = _LIBRARY_FILES.replace(
    "open_library(root).put(env)\n",
    "library = open_library(root)\nlibrary.put(env)\nlibrary.set_ref('sample-run', 'scope/base', env.id)\n",
).replace(
    "for p in sorted(root.rglob('*')):\n",
    "for p in [root / 'library' / 'index.sqlite', root / 'library' / 'refs' / 'sample-run' / 'scope' / 'base']:\n",
)


@posix_only
def test_library_lock_and_ref_files_are_owner_only_under_umask_zero(tmp_path: Path) -> None:
    """The lock file is pre-created by `open_private` before SQLite opens it; refs come from the
    atomic writer."""
    assert "set_ref" in _LIBRARY_LOCK and "index.sqlite" in _LIBRARY_LOCK
    got = _run(_LIBRARY_LOCK, str(tmp_path)).splitlines()
    assert got == ["file 0o600", "file 0o600", "root 0o700"]
