"""The library's one filesystem module: every read, write, replace, list and remove under a root.

Every call names the library root (the `.decoy` folder) and a path lexically inside it. Each
component below the root is judged with `lstat` and must be a real folder: a symlink, a Windows
reparse point (junction), a file or a pipe in the middle of the path is refused with
`library_path_unsafe` before anything is read, written or removed, so nothing reaches outside the
root through a planted link. The root itself is the trusted anchor (the user chose it).

A remove re-walks the path right before it acts and, given the inode fsck judged, leaves an
entry that was replaced since. `remove_tree` enters only real folders; a link inside the tree is
removed as an entry, never entered. Named limit: the walk and the call are separate steps, so a
same-user process that swaps a folder for a link in between is not stopped (descriptor walks
would close it, but no-follow opens belong to the one small-file reader).

Writes go through `decoy._atomic` (G-ONE-ATOMIC-WRITER) and reads through
`decoy.cli.io.read_small_file` (no-follow on the last component, a cap per file kind); this
module adds the check of every component before them. Folders come from
`decoy._private_file.create_private_directory` (0700 at creation; an existing folder is never
re-permissioned). G-LIB-FS (`tests/sentry/io_policy/test_library_fs.py`) holds that no other
library module removes, renames or writes a file itself.

Every failure leaves as `LibraryError` with a code and the error class, raised after the
`except` block so no path text is chained.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal

from decoy._atomic import (
    ATOMIC_TARGET_BUSY,
    AtomicWriteError,
    WriteMode,
    destination_entry,
    write_atomic,
    write_local_target,
)
from decoy._private_file import (
    PRIVATE_EXISTS,
    PrivateFileError,
    create_private_directory,
    open_private,
)
from decoy.cli.io import UnsafeFileError, read_small_file
from decoy.cli.library._errors import (
    EXPORT_DESTINATION_UNSAFE,
    LIBRARY_BUSY,
    LIBRARY_FILE_TOO_LARGE,
    LIBRARY_PATH_UNSAFE,
    LIBRARY_READ_FAILED,
    LIBRARY_WRITE_FAILED,
    LibraryError,
    library_error,
)

__all__ = [
    "Entry",
    "Kind",
    "anchor",
    "checked_file",
    "clear_tree",
    "ensure_private_dir",
    "entries",
    "entry_of",
    "kind_of",
    "nearest_existing",
    "open_database",
    "open_database_readonly",
    "read_capped",
    "remove_file",
    "remove_tree",
    "replace_file",
    "require_dirs",
    "walk_tree",
    "write_dotfile_once",
    "write_export",
    "write_once",
]

Kind = Literal["file", "dir", "link", "other"]
_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: a symlink or a junction on Windows


@dataclass(frozen=True)
class Entry:
    """One directory entry, judged without following it."""

    name: str
    path: Path
    kind: Kind
    inode: tuple[int, int]
    size: int
    mtime: float
    mode: int


def _kind(info: os.stat_result) -> Kind:
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        return "link"
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    if stat.S_ISREG(info.st_mode):
        return "file"
    return "other"


def _unsafe() -> LibraryError:
    return LibraryError(LIBRARY_PATH_UNSAFE)


def _parts(root: Path, path: Path) -> tuple[str, ...]:
    """`path`'s components below `root`, lexically; `library_path_unsafe` when it is not inside.

    Nothing is resolved: `..` is collapsed by text, so a path cannot climb out by naming its
    parent, and a link is judged by the walk, never followed to decide containment.
    """
    base = PurePath(os.path.normpath(root))
    target = PurePath(os.path.normpath(path))
    if not target.is_absolute() and base.is_absolute():
        target = base / target
    try:
        parts = target.relative_to(base).parts
    except ValueError:
        parts = ("..",)
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise _unsafe()
    return parts


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None


def _walk(root: Path, parts: tuple[str, ...]) -> bool:
    """True when every folder in `parts` exists as a real folder below `root`; False at the
    first missing one. A link, junction or non-folder on the way is `library_path_unsafe`."""
    current = Path(root)
    for name in parts:
        current = current / name
        info = _lstat(current)
        if info is None:
            return False
        if _kind(info) != "dir":
            raise _unsafe()
    return True


def require_dirs(root: Path, path: Path) -> bool:
    """`path` and every folder above it, up to `root`, are real folders; False when one is
    missing. `library_path_unsafe` for a link, a junction or anything else on the way."""
    return _walk(root, _parts(root, path))


def _require_parent(root: Path, path: Path) -> tuple[tuple[str, ...], bool]:
    parts = _parts(root, path)
    return parts, _walk(root, parts[:-1])


def anchor(path: Path) -> Path:
    """The library root as an absolute path, links in it resolved. The root is the one path whose
    links are followed: the user chose it, and every path below it is judged from it. A path that
    cannot be resolved (a link loop, a NUL byte) is `library_path_unsafe`."""
    resolved: Path | None
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        resolved = None
    if resolved is None:
        raise _unsafe()
    return resolved


def nearest_existing(path: Path) -> Path:
    """`path`, or its nearest ancestor that exists (a root not made yet): what the filesystem
    probe asks about. Reads no library file."""
    for candidate in (Path(path), *Path(path).parents):
        if os.path.exists(candidate):
            return candidate
    return Path(path)


def entry_of(root: Path, path: Path) -> Entry | None:
    """What sits at `path` (never following it), with its inode, size and mode; None when it, or
    a folder above it, is missing. A link or non-folder above it is `library_path_unsafe`."""
    if not _require_parent(root, path)[1]:
        return None
    info = _lstat(path)
    if info is None:
        return None
    return Entry(
        Path(path).name,
        Path(path),
        _kind(info),
        (info.st_dev, info.st_ino),
        info.st_size,
        info.st_mtime,
        stat.S_IMODE(info.st_mode),
    )


def checked_file(root: Path, path: Path) -> Path:
    """`path` for a caller that must open it by name (SQLite opens its database by path): every
    folder above it is a real folder and what is there, if anything, is a regular file.
    `library_path_unsafe` otherwise, so the open can neither follow a link nor block on a pipe."""
    found = entry_of(root, path)
    if found is not None and found.kind != "file":
        raise _unsafe()
    return Path(path)


def open_database(root: Path, path: Path, *, truncate: bool, timeout: float) -> sqlite3.Connection:
    """Open the SQLite file at `path` for the library lock: `checked_file` judges the path, the
    file is pre-created 0600 with `open_private` (emptied in place when `truncate`, so it stays
    one inode and one lock), then SQLite opens it. Raises `PrivateFileError` or
    `sqlite3.Error` for the index to classify, `library_path_unsafe` for a linked path."""
    checked = checked_file(root, path)
    open_private(checked, new_parent=False, truncate=truncate)
    return sqlite3.connect(str(checked), timeout=timeout, isolation_level=None)


def open_database_readonly(root: Path, path: Path) -> sqlite3.Connection:
    """A read-only SQLite connection to the judged file at `path` (fsck never creates one)."""
    checked = checked_file(root, path)
    return sqlite3.connect(f"{Path(os.path.abspath(checked)).as_uri()}?mode=ro", uri=True)


def kind_of(root: Path, path: Path) -> Kind | None:
    """What sits at `path`, never following it; None when it, or a folder above it, is missing."""
    present = _require_parent(root, path)[1]
    if not present:
        return None
    info = _lstat(path)
    return None if info is None else _kind(info)


def entries(root: Path, folder: Path) -> list[Entry] | None:
    """The entries of the real folder `folder`, sorted by name, each judged by `lstat`.

    None when the folder is missing. A link or a non-folder at `folder` or above it is
    `library_path_unsafe`: the caller reports it and never descends through it.
    """
    if not require_dirs(root, folder):
        return None
    found: list[Entry] = []
    failure: OSError | None = None
    try:
        found = _scan(folder)
    except OSError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_READ_FAILED, failure)
    return sorted(found, key=lambda e: e.name)


def walk_tree(root: Path, folder: Path, *, unreadable: list[Path] | None = None) -> list[Entry]:
    """`folder` and every entry below it, depth first, never descending through a link.

    Empty when `folder` is missing; `library_path_unsafe` when it, or a folder above it, is a
    link or not a folder. A link inside the tree is listed as a `link` entry and not entered.
    With `unreadable`, a folder below `folder` that cannot be listed is added there and skipped
    instead of failing the walk.
    """
    top = kind_of(root, folder)
    if top is None:
        return []
    if top != "dir":
        raise _unsafe()
    info = os.lstat(folder)
    out = [
        Entry(
            Path(folder).name,
            Path(folder),
            "dir",
            (info.st_dev, info.st_ino),
            info.st_size,
            info.st_mtime,
            stat.S_IMODE(info.st_mode),
        )
    ]
    pending = [Path(folder)]
    while pending:
        current = pending.pop()
        try:
            found = entries(root, current) or []
        except LibraryError:
            if unreadable is None:
                raise
            unreadable.append(current)
            continue
        for item in found:
            out.append(item)
            if item.kind == "dir":
                pending.append(item.path)
    return out


def ensure_private_dir(root: Path, path: Path) -> None:
    """Make `path` an owner-only folder if it is missing; its parent must be a real folder.

    `path` may be `root` itself, whose parent is outside the library and is not judged.

    An existing real folder (another writer's, or the user's) is accepted as it is; a link or a
    file in its place is `library_path_unsafe`.
    """
    is_root = os.path.normpath(root) == os.path.normpath(path)
    if not is_root and not _require_parent(root, path)[1]:
        raise LibraryError(LIBRARY_WRITE_FAILED, "FileNotFoundError")
    failure: BaseException | None = None
    try:
        create_private_directory(path)
    except PrivateFileError as exc:
        if exc.code != PRIVATE_EXISTS:
            failure = exc
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    if is_root:  # the anchor the user chose: a link to a folder is accepted there only
        if not os.path.isdir(path):
            raise _unsafe()
        return
    info = _lstat(path)
    if info is None or _kind(info) != "dir":
        raise _unsafe()


def write_once(root: Path, directory: Path, name: str, data: bytes, *, tmp_dir: Path) -> bool:
    """Create `directory/name` with `data` unless it exists; True when this call created it.

    False means a file was already there; the caller verifies it.
    """
    return _write(root, directory, name, data, WriteMode.CREATE_ONCE, tmp_dir=tmp_dir)


def replace_file(root: Path, directory: Path, name: str, data: bytes, *, tmp_dir: Path) -> None:
    """Replace `directory/name` with `data` in one step (refs, plan 4.9 `REPLACE`).

    On Windows a target another program holds open is retried by `_atomic` (bounded backoff,
    about one second); still held after that, the writer says `atomic_target_busy` and this is
    `library_busy`. Every other failure, an ACL deny included, is `library_write_failed`.
    """
    _write(root, directory, name, data, WriteMode.REPLACE, tmp_dir=tmp_dir)


def _write(
    root: Path, directory: Path, name: str, data: bytes, mode: WriteMode, *, tmp_dir: Path
) -> bool:
    for folder in (directory, tmp_dir):
        if not require_dirs(root, folder):
            raise LibraryError(LIBRARY_WRITE_FAILED, "FileNotFoundError")
    _parts(root, Path(directory) / name)
    failure: AtomicWriteError | None = None
    created = False
    try:
        created = write_atomic(directory, name, data, mode, tmp_dir=tmp_dir)
    except AtomicWriteError as exc:
        failure = exc
    if failure is None:
        return created
    code = LIBRARY_BUSY if failure.code == ATOMIC_TARGET_BUSY else LIBRARY_WRITE_FAILED
    raise library_error(code, failure)


def write_dotfile_once(root: Path, path: Path, data: bytes) -> bool:
    """Create the dot-named file `path` unless it exists; an existing one is never edited."""
    present = _require_parent(root, path)[1]
    if not present:
        raise LibraryError(LIBRARY_WRITE_FAILED, "FileNotFoundError")
    return _write_local(path, data, WriteMode.CREATE_ONCE)


def write_export(root: Path, out: Path, data: bytes) -> None:
    """Write `data` to the file the user named (`export --output`), replacing it in one step,
    0600; the one checked entry point for a path outside the library.

    Where the bytes would land comes from `_atomic.destination_entry` (the parent resolved
    strictly, the final name not followed), the shared output-placement rule. A landing inside
    `library/` or `scratch/`, named directly or through a linked folder, or a final symlink, is
    `export_destination_unsafe` and nothing is written.
    """
    named = Path(os.path.abspath(out))
    lexical = [Path(os.path.abspath(Path(root) / name)) for name in ("library", "scratch")]
    unsafe = any(g == named or g in named.parents for g in lexical)
    landing: Path | None = None
    failure: Exception | None = None
    try:
        landing = destination_entry(out)
        guarded = [_resolved(Path(root) / name) for name in ("library", "scratch")]
        inside = any(g == landing or g in landing.parents for g in guarded)
        there = _lstat(landing)
        unsafe = unsafe or inside or (there is not None and _kind(there) == "link")
    except (OSError, ValueError) as exc:
        failure = exc
    if failure is not None and not unsafe:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    if unsafe or landing is None:
        raise LibraryError(EXPORT_DESTINATION_UNSAFE)
    _write_local(landing, data, WriteMode.REPLACE)


def _resolved(path: Path) -> Path:
    """`path` with every existing link in it followed: where a guarded folder really is."""
    return Path(os.path.realpath(path))


def _write_local(path: Path, data: bytes, mode: WriteMode) -> bool:
    failure: AtomicWriteError | None = None
    created = False
    try:
        created = write_local_target(path, data, mode)
    except AtomicWriteError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    return created


def read_capped(root: Path, path: Path, max_bytes: int) -> bytes | None:
    """The bytes of the plain regular file at `path`, or None when nothing is there.

    Every folder above it must be a real folder (`library_path_unsafe` otherwise). The read goes
    through the CLI's one small-file reader (`decoy.cli.io.read_small_file`), so a symlink, FIFO,
    device or a file swapped between check and open is refused and never followed or waited on
    (`library_read_failed`). A file over `max_bytes` is refused unread past the cap
    (`library_file_too_large`); a file whose length changed during the read is refused too.
    """
    present = _require_parent(root, path)[1]
    if not present:
        return None
    failure: UnsafeFileError | None = None
    found = None
    try:
        found = read_small_file(path, max_bytes + 1)
    except UnsafeFileError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_READ_FAILED, failure)
    if found is None:
        return None
    if found.size > max_bytes or len(found.data) > max_bytes:
        raise LibraryError(LIBRARY_FILE_TOO_LARGE)
    if len(found.data) != found.size:
        raise LibraryError(LIBRARY_READ_FAILED)
    return found.data


def _rmtree_walk(path: Path) -> None:
    """Every entry judged by lstat, the shape of CPython's `shutil._rmtree_unsafe` with its link
    rule tightened: a link or junction is removed as an entry (its target untouched) and never
    entered."""
    for item in _scan(path):
        if item.kind == "dir":
            _rmtree_walk(item.path)
        elif item.kind == "link" and stat.S_ISDIR(os.lstat(item.path).st_mode):
            os.rmdir(item.path)  # a directory link or junction: rmdir drops the link only
        else:
            os.unlink(item.path)
    os.rmdir(path)


def _scan(folder: Path) -> list[Entry]:
    """Every entry of `folder`, judged by lstat (the caller has judged `folder` itself)."""
    out: list[Entry] = []
    with os.scandir(folder) as listing:
        for item in listing:
            info = item.stat(follow_symlinks=False)
            out.append(
                Entry(
                    item.name,
                    Path(folder) / item.name,
                    _kind(info),
                    (info.st_dev, info.st_ino),
                    info.st_size,
                    info.st_mtime,
                    stat.S_IMODE(info.st_mode),
                )
            )
    return out


def remove_file(root: Path, path: Path, *, inode: tuple[int, int] | None = None) -> bool:
    """Remove the entry at `path` (a file, or a link itself, never its target).

    False when it is already gone, or when `inode` is given and the entry there now is another
    one (it was replaced since the caller judged it). A folder there, or a link or non-folder
    above it, is `library_path_unsafe`. Any other failure is `library_write_failed`.
    """
    parts, present = _require_parent(root, path)
    if not present:
        return False
    failure: OSError | None = None
    unsafe = False
    try:
        info = os.lstat(path)
        if _kind(info) == "dir":
            unsafe = True
        elif inode is None or (info.st_dev, info.st_ino) == inode:
            os.unlink(path)
            return True
        else:
            return False
    except FileNotFoundError:
        return False
    except OSError as exc:
        unsafe = _swapped(root, parts)
        failure = exc
    if unsafe:
        raise _unsafe()
    raise library_error(LIBRARY_WRITE_FAILED, failure)


def remove_tree(root: Path, path: Path) -> bool:
    """Remove the real folder `path` and everything in it; False when it is already gone.

    A link or junction at `path` or above it is `library_path_unsafe` and nothing is removed; a
    link inside the tree is removed as an entry and never entered.
    """
    parts, present = _require_parent(root, path)
    if not present:
        return False
    info = _lstat(path)
    if info is None:
        return False
    if _kind(info) != "dir":
        raise _unsafe()
    failure: OSError | None = None
    unsafe = False
    try:
        _rmtree_walk(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        unsafe = _swapped(root, (*parts, ""))
        failure = exc
    if unsafe:
        raise _unsafe()
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    return True


def clear_tree(root: Path, folder: Path) -> tuple[int, tuple[str, ...]]:
    """Remove the real folder `folder` file by file, best effort: (files removed, files left).

    A file the OS will not remove (held open by another program on Windows: `PermissionError`)
    is left and named in the result, relative to `folder`, and never raises; the next cleanup
    removes it. A link inside is removed as an entry and never entered. A link or non-folder at
    `folder` or above it is `library_path_unsafe` and nothing is removed.
    """
    present = _require_parent(root, folder)[1]
    info = _lstat(folder) if present else None
    if info is None:
        return 0, ()
    if _kind(info) != "dir":
        raise _unsafe()
    removed = 0
    skipped: list[str] = []
    pending = [Path(folder)]
    order: list[Path] = []
    while pending:
        current = pending.pop()
        order.append(current)
        for item in entries(root, current) or []:
            if item.kind == "dir":
                pending.append(item.path)
                continue
            try:
                if item.kind == "link" and stat.S_ISDIR(os.lstat(item.path).st_mode):
                    os.rmdir(item.path)  # a Windows junction: rmdir drops the link only
                else:
                    os.unlink(item.path)
                removed += 1
            except FileNotFoundError:
                pass
            except PermissionError:
                skipped.append(item.path.relative_to(folder).as_posix())
    for current in reversed(order):
        try:
            os.rmdir(current)
        except OSError:
            pass  # still holds a skipped file
    return removed, tuple(sorted(skipped))


def _swapped(root: Path, parts: tuple[str, ...]) -> bool:
    """After a remove failed: True when a folder on the way is now a link or not a folder (it
    was swapped since the walk), so the failure is a refusal, not an I/O error."""
    try:
        _walk(root, parts[:-1])
    except LibraryError:
        return True
    return False
