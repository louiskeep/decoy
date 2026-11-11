"""Is the library root on a network filesystem? (plan 4.8; L1c.1)

On SMB, NFS and similar mounts a SQLite lock can appear to succeed without excluding other
writers (sqlite.org/useovernet.html), so a detected remote root runs in degraded mode: record
writes continue, ref updates (and later prune and clean) refuse with `library_lock_unavailable`.
The probe runs once per `open_library`.

- Linux: `statfs(2)` `f_type`, matched against the kernel's magic numbers in
  `include/uapi/linux/magic.h` (NFS_SUPER_MAGIC 0x6969, SMB_SUPER_MAGIC 0x517B, AFS_SUPER_MAGIC
  0x5346414F, AFS_FS_MAGIC 0x6B414653, V9FS_MAGIC 0x01021997) and the filesystems' own headers
  (`fs/smb/common/smb2pdu.h` SMB2_SUPER_MAGIC 0xFE534D42, `fs/smb/client/cifsglob.h`
  CIFS_SUPER_MAGIC 0xFF534D42, `fs/fuse/inode.c` FUSE_SUPER_MAGIC 0x65735546). `os.statvfs` has
  no `f_type`, so libc `statfs` is called through `ctypes`; `f_type` is the first member of
  `struct statfs` on every Linux ABI, read as a C `long`.
- macOS: `statfs(2)` `f_fstypename` (`nfs`, `smbfs`, `afpfs`, `webdav`), from the 64-bit-inode
  `struct statfs` in `<sys/mount.h>` (`f_fstypename` at byte 72).
- Windows: a UNC path, or `GetDriveTypeW` on the path's root returning `DRIVE_REMOTE` (4).

`ctypes` use is the minimum for those three calls. A probe that fails reads as local: degraded
mode is for a positive detection, so an unprobeable local disk keeps working. A synced folder
(OneDrive, Dropbox) is local to the OS and is not detected (plan non-goals). The macOS and
Windows live calls run only in their lanes.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from pathlib import Path

__all__ = ["linux_remote", "macos_remote", "remote_filesystem", "windows_remote"]

_PLATFORM = sys.platform  # a module attribute so tests can dispatch to each branch

LINUX_REMOTE_MAGIC: dict[int, str] = {
    0x6969: "nfs",
    0x517B: "smb",
    0xFE534D42: "smb2",
    0xFF534D42: "cifs",
    0x5346414F: "afs",
    0x6B414653: "afs",
    0x01021997: "9p",
    0x65735546: "fuse",
}
MACOS_REMOTE = frozenset({"nfs", "smbfs", "afpfs", "webdav"})
DRIVE_REMOTE = 4
_STATFS_BYTES = 4096  # larger than any platform's struct statfs
_MACOS_FSTYPENAME = slice(72, 88)


def linux_remote(magic: int) -> str | None:
    return LINUX_REMOTE_MAGIC.get(magic & 0xFFFFFFFF)


def macos_remote(fstype: str) -> str | None:
    return fstype if fstype in MACOS_REMOTE else None


def windows_remote(path: str, drive_type: int) -> str | None:
    if path.startswith(("\\\\", "//")):
        return "unc"
    return "remote_drive" if drive_type == DRIVE_REMOTE else None


def _libc() -> ctypes.CDLL:
    return ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)


def _statfs_buffer(path: Path, symbol: str) -> bytes:
    libc = _libc()
    call = getattr(libc, symbol)
    buf = ctypes.create_string_buffer(_STATFS_BYTES)
    if call(os.fsencode(path), buf) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return buf.raw


def _linux_magic(path: Path) -> int:
    return ctypes.c_long.from_buffer_copy(_statfs_buffer(path, "statfs")).value


def _macos_type(path: Path) -> str:
    # The 64-bit-inode statfs is exported as `statfs$INODE64` on x86_64, `statfs` on arm64.
    libc = _libc()
    symbol = "statfs$INODE64" if hasattr(libc, "statfs$INODE64") else "statfs"
    raw = _statfs_buffer(path, symbol)[_MACOS_FSTYPENAME]
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def _windows_drive_type(path: Path) -> int:
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    return int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))


def _existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path


def remote_filesystem(path: Path) -> str | None:
    """The remote filesystem name under `path` (its nearest existing folder), or None."""
    target = _existing(path)
    try:
        if _PLATFORM.startswith("linux"):
            return linux_remote(_linux_magic(target))
        if _PLATFORM == "darwin":
            return macos_remote(_macos_type(target))
        if _PLATFORM == "win32":
            return windows_remote(os.path.abspath(target), _windows_drive_type(target))
    except (OSError, AttributeError, ValueError):
        return None
    return None
