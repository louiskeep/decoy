"""Library scratch: the only Decoy area that holds rows (plan 4.6, 4.7, 3 "Protected scratch"; L1d).

Every directory here comes from the engine's one row-directory allocator (L0, public):
`decoy_engine.open_protected_dir` for `scratch/` itself, reopened and checked on every command (an
empty too-open one is tightened, a too-open one with files in it is refused), and per allocation
either `protected_scratch_dir` (a fresh directory removed on every exit: `delete_on_exit` staging)
or `open_protected_dir` at `<owner>-<invocation_id>` (kept until its TTL: sample output). The
engine creates them owner-only from their first instant (POSIX 0700; a protected DACL on Windows)
and fails closed with `scratch_acl_failed` or `scratch_unsafe`: no directory is left and the
owner's block never runs, so no row is written. The CLI has no `mkdir`, `chmod` or `ctypes` here.

A fresh allocation is named by the engine: `<owner>-<invocation_id>-` plus 16 hex digits (the
engine adds a random token to every fresh directory), not the plan's bare `<owner>-<invocation_id>`.

Deletes are best effort, file by file (plan 4.7): a file another program holds open (a sample
open in Excel on Windows raises `PermissionError`) is skipped and reported under the engine's
`library_delete_skipped` warning code, never raised; the next cleanup removes it. `.decoy/.gitignore`
ignores `scratch/` (written by `Library.prepare` before `scratch/` exists).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from decoy_engine import DecoyError, open_protected_dir, protected_scratch_dir
from decoy_engine.reasons import runtime, warning

from decoy.cli.library._errors import LIBRARY_WRITE_FAILED, LibraryError, library_error
from decoy.cli.library._fs import replace_file
from decoy.cli.library._paths import SCRATCH

if TYPE_CHECKING:
    from decoy.cli.library._store import Library

__all__ = ["DeleteReport", "ScratchAllocation", "allocate", "clean_all", "delete_tree"]

_OWNER = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_ENGINE_CODES = frozenset({runtime.SCRATCH_ACL_FAILED, runtime.SCRATCH_UNSAFE})


@dataclass(frozen=True)
class DeleteReport:
    """`skipped` names the files left behind, relative to the deleted folder; `code` is the
    engine's `library_delete_skipped` when there are any."""

    removed: int
    skipped: tuple[str, ...]

    @property
    def code(self) -> str | None:
        return warning.LIBRARY_DELETE_SKIPPED if self.skipped else None


@dataclass
class ScratchAllocation:
    """One allocation. `report` and `skipped` are set when a delete-on-exit block ends."""

    path: Path
    kept: bool
    report: DeleteReport | None = field(default=None)

    @property
    def skipped(self) -> tuple[str, ...]:
        return self.report.skipped if self.report is not None else ()

    def write(self, name: str, data: bytes) -> None:
        """Write one file in the allocation, 0600 through the atomic writer."""
        replace_file(self.path, name, data, tmp_dir=self.path)


def delete_tree(folder: Path) -> DeleteReport:
    """Remove `folder` file by file; skip and report what cannot be removed. Never raises for a
    file that is held open."""
    removed = 0
    skipped: list[str] = []
    if folder.is_symlink() or folder.is_file():
        try:
            os.unlink(folder)
        except FileNotFoundError:
            return DeleteReport(0, ())
        except PermissionError:
            return DeleteReport(0, (folder.name,))
        return DeleteReport(1, ())
    if not folder.exists():
        return DeleteReport(0, ())
    for current, dirs, files in os.walk(folder, topdown=False):
        base = Path(current)
        for name in files:
            try:
                os.unlink(base / name)
                removed += 1
            except FileNotFoundError:
                pass
            except PermissionError:
                skipped.append((base / name).relative_to(folder).as_posix())
        for name in dirs:
            try:
                os.rmdir(base / name)
            except OSError:
                pass  # still holds a skipped file
    try:
        os.rmdir(folder)
    except OSError:
        pass
    return DeleteReport(removed, tuple(sorted(skipped)))


def _scratch_root(library: Library) -> Path:
    library.prepare()  # the root and its .gitignore come first, so scratch/ is never committed
    return _opened(library.root / SCRATCH)


def _engine_failure(exc: BaseException) -> LibraryError:
    code = getattr(exc, "code", None)
    if isinstance(exc, DecoyError) and code in _ENGINE_CODES:
        return library_error(str(code), exc)
    return library_error(LIBRARY_WRITE_FAILED, exc)


def _opened(path: Path) -> Path:
    failure: BaseException | None = None
    try:
        return open_protected_dir(path, create=True)
    except (DecoyError, OSError) as exc:
        failure = exc
    raise _engine_failure(failure or OSError())


@contextmanager
def allocate(
    library: Library, owner: str, invocation_id: str, ttl: timedelta | None
) -> Iterator[ScratchAllocation]:
    """See `Library.scratch`."""
    if not _OWNER.fullmatch(owner) or "/" in invocation_id or os.sep in invocation_id:
        raise ValueError("owner must match [a-z0-9][a-z0-9-]{0,31}")
    scratch = _scratch_root(library)
    name = f"{owner}-{invocation_id}"
    if ttl is not None:
        yield ScratchAllocation(_opened(scratch / name), kept=True)
        return
    failure: BaseException | None = None
    fresh = None
    try:
        fresh = protected_scratch_dir(scratch, f"{name}-")
        path = fresh.__enter__()
    except (DecoyError, OSError) as exc:
        failure = exc
    if failure is not None or fresh is None:
        raise _engine_failure(failure or OSError())
    alloc = ScratchAllocation(path, kept=False)
    try:
        yield alloc
    finally:
        alloc.report = delete_tree(path)  # reports what is held open, then the engine removes
        fresh.__exit__(None, None, None)


def clean_all(library: Library) -> list[tuple[str, DeleteReport]]:
    """Remove everything under `scratch/`, entry by entry, under the library lock
    (`decoy library clean --yes`). Returns each entry's name and what was left behind. Raises
    `LibraryError` (`library_lock_unavailable`, `library_busy`)."""
    from decoy.cli.library import _index
    from decoy.cli.library._errors import LIBRARY_LOCK_UNAVAILABLE

    if library.degraded is not None:
        raise LibraryError(LIBRARY_LOCK_UNAVAILABLE)
    scratch = library.root / SCRATCH
    if not scratch.is_dir():
        return []
    results: list[tuple[str, DeleteReport]] = []
    with _index.locked(library.library_dir):
        for entry in sorted(scratch.iterdir()):
            results.append((entry.name, library.delete_scratch(entry)))
    return results
