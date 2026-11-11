"""The remote-filesystem probe (plan 4.8; L1c.1): which roots run in degraded mode.

The classification tables are tested on every OS; the live probe runs on this OS only. The
Windows and macOS live calls are written but run only in their lanes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from decoy.cli.library import _remote


@pytest.mark.parametrize(
    ("magic", "name"),
    [
        (0x6969, "nfs"),
        (0x517B, "smb"),
        (0xFE534D42, "smb2"),
        (0xFF534D42, "cifs"),
        (0x5346414F, "afs"),
        (0x6B414653, "afs"),
        (0x01021997, "9p"),
        (0x65735546, "fuse"),
        (0xEF53, None),  # ext2/3/4
        (0x58465342, None),  # xfs
        (0x01021994, None),  # tmpfs
        (0x9123683E, None),  # btrfs
    ],
)
def test_linux_magic_numbers(magic: int, name: str | None) -> None:
    assert _remote.linux_remote(magic) == name


@pytest.mark.parametrize(
    ("fstype", "name"),
    [("nfs", "nfs"), ("smbfs", "smbfs"), ("afpfs", "afpfs"), ("webdav", "webdav"),
     ("apfs", None), ("hfs", None), ("msdos", None)],
)  # fmt: skip
def test_macos_type_names(fstype: str, name: str | None) -> None:
    assert _remote.macos_remote(fstype) == name


@pytest.mark.parametrize(
    ("path", "drive_type", "name"),
    [
        ("\\\\server\\share\\proj", 3, "unc"),
        ("//server/share/proj", 3, "unc"),
        ("Z:\\proj", 4, "remote_drive"),
        ("C:\\proj", 3, None),
    ],
)
def test_windows_drive_rule(path: str, drive_type: int, name: str | None) -> None:
    assert _remote.windows_remote(path, drive_type) == name


def test_the_probe_dispatches_on_the_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_remote, "_linux_magic", lambda p: calls.append("linux") or 0x6969)
    monkeypatch.setattr(_remote, "_macos_type", lambda p: calls.append("macos") or "smbfs")
    monkeypatch.setattr(_remote, "_windows_drive_type", lambda p: calls.append("win") or 4)
    monkeypatch.setattr(_remote, "_PLATFORM", "linux")
    assert _remote.remote_filesystem(tmp_path) == "nfs"
    monkeypatch.setattr(_remote, "_PLATFORM", "darwin")
    assert _remote.remote_filesystem(tmp_path) == "smbfs"
    monkeypatch.setattr(_remote, "_PLATFORM", "win32")
    assert _remote.remote_filesystem(tmp_path) == "remote_drive"
    assert calls == ["linux", "macos", "win"]


def test_a_missing_root_is_probed_at_its_nearest_existing_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []
    monkeypatch.setattr(_remote, "_PLATFORM", "linux")
    monkeypatch.setattr(_remote, "_linux_magic", lambda p: seen.append(p) or 0xEF53)
    assert _remote.remote_filesystem(tmp_path / "a" / "b" / ".decoy") is None
    assert seen == [tmp_path]


def test_a_probe_that_fails_reads_as_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_p: Path) -> int:
        raise OSError(5, "no")

    monkeypatch.setattr(_remote, "_PLATFORM", "linux")
    monkeypatch.setattr(_remote, "_linux_magic", boom)
    assert _remote.remote_filesystem(tmp_path) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux statfs")
def test_the_live_linux_probe_reads_a_magic_number(tmp_path: Path) -> None:
    magic = _remote._linux_magic(tmp_path)
    assert isinstance(magic, int) and magic > 0  # non-vacuous: statfs really answered
    assert _remote.remote_filesystem(tmp_path) == _remote.linux_remote(magic)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS lane: statfs f_fstypename")
def test_the_live_macos_probe_reads_a_type_name(tmp_path: Path) -> None:
    name = _remote._macos_type(tmp_path)
    assert isinstance(name, str) and name


@pytest.mark.skipif(sys.platform != "win32", reason="Windows lane: GetDriveTypeW")
def test_the_live_windows_probe_reads_a_drive_type(tmp_path: Path) -> None:
    assert _remote._windows_drive_type(tmp_path) in {2, 3, 4, 5, 6}
