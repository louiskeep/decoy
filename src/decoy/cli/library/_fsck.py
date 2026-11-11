"""`decoy library fsck [--repair]`: check a library against its own rules (plan 4.10; L1c.2).

The shape is `git fsck`: read-only by default, every problem one line with a stable code and a
target relative to the library root, and a separate repair step that never deletes a valid
record. Checks:

- every object's id, by the one id rule (`Library.get` parses before hashing, so a CRLF copy
  passes), its envelope, and its payload against the read model (an opaque kind by id only);
- every ref points at a stored record; every link target exists (a dangling link is a warning,
  since prune may remove an unprotected target);
- the index matches the objects it can hold (read-only `mode=ro` open, never created here);
- no temp file under `library/tmp/` is older than an hour;
- POSIX modes: the index, `tmp/`, `scratch/` and `logs/` must be private (a finding); records
  and refs get an advisory note, since git checks them out 0644 and they hold no values (4.6);
- job log lines parse (`records.read_job_log`); a truncated last line is a warning.

`repair` copies each corrupt object into `library/quarantine/` through the atomic writer and only
then removes it (nothing is moved by a raw rename; G-ONE-ATOMIC-WRITER), deletes stale temp
files, removes refs to missing records under the library lock, and rebuilds the index. A library
whose `LAYOUT` this version does not write is reported and never repaired.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import stat
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from decoy_engine import records

from decoy.cli.library import _index, _refs
from decoy.cli.library._errors import RECORD_INVALID, LibraryError
from decoy.cli.library._fs import ensure_private_dir, read_file, write_once
from decoy.cli.library._paths import (
    INDEX_FILE,
    LAYOUT_FILE,
    LAYOUT_VERSION,
    LIBRARY,
    LOGS,
    OBJECTS,
    QUARANTINE,
    REFS,
    SCRATCH,
    TMP,
    record_digest,
)
from decoy.cli.library._store import Library, open_library

__all__ = ["Action", "Finding", "FsckReport", "check", "repair"]

Level = Literal["finding", "warning", "note"]
STALE_TEMP_SECONDS = 3600  # the git `gc.pruneExpire` idea, scaled to a write's lifetime
_SUFFIX = ".json"
_POSIX = sys.platform != "win32"
_CORRUPT_CODES = frozenset({"object_corrupt", "object_name_invalid"})


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    target: str  # relative to the library root, or a record id


@dataclass(frozen=True)
class Action:
    code: str
    target: str


@dataclass(frozen=True)
class FsckReport:
    items: tuple[Finding, ...]
    objects: int

    @property
    def clean(self) -> bool:
        return not any(f.level == "finding" for f in self.items)


class _Walk:
    """One read-only pass over a library root."""

    def __init__(self, root: Path, now: float) -> None:
        self.root = root
        self.lib = root / LIBRARY
        self.now = now
        self.items: list[Finding] = []
        self.library = Library(root)  # no open: fsck must not catch the index up first
        self.present: set[str] = set()
        self.indexable: set[str] = set()
        self.objects = 0

    def add(self, level: Level, code: str, path_or_id: Path | str) -> None:
        target = path_or_id if isinstance(path_or_id, str) else self.rel(path_or_id)
        self.items.append(Finding(level, code, target))

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def layout_newer(self) -> bool:
        data = read_file(self.lib / LAYOUT_FILE)
        if data is None:
            return False
        found: object = None
        with contextlib.suppress(ValueError):
            found = json.loads(data)
        version = found.get("layout") if isinstance(found, dict) else None
        if version == LAYOUT_VERSION and not isinstance(version, bool):
            return False
        self.add("finding", "layout_newer", self.lib / LAYOUT_FILE)
        return True

    def objects_and_links(self) -> None:
        links: list[tuple[str, str]] = []
        for path, record_id in _object_files(self.lib / OBJECTS):
            if record_id is None:
                self.add("finding", "object_name_invalid", path)
                continue
            self.objects += 1
            self.present.add(record_id)
            decoded: object = None
            code: str | None = None
            try:
                decoded = self.library.get(record_id)
            except LibraryError as exc:
                code = exc.code
            if code is not None:
                bad = "payload_invalid" if code == RECORD_INVALID else "object_corrupt"
                self.add("finding", bad, path)
            elif isinstance(decoded, records.RecordNeedsNewer):
                self.add("warning", "needs_newer", path)
            else:
                self.indexable.add(record_id)
                raw = getattr(decoded, "raw", {})
                links += [(record_id, str(link.get("id"))) for link in raw.get("links") or ()]
        for src, dst in links:
            if dst not in self.present:
                self.add("warning", "link_dangling", src)

    def refs(self) -> None:
        for path, record_id in _refs.iter_refs(self.lib / REFS):
            if record_id is None:
                self.add("finding", "ref_corrupt", path)
            elif record_id not in self.present:
                self.add("finding", "ref_dangling", path)

    def index(self) -> None:
        path = self.lib / INDEX_FILE
        if not path.exists():
            if self.present:
                self.add("finding", "index_missing", path)
            return
        found = _indexed_ids(path)
        if found is None:
            self.add("finding", "index_corrupt", path)
            return
        version, ids = found
        if version != _index.SCHEMA_VERSION or (self.indexable - ids) or (ids - self.present):
            self.add("finding", "index_stale", path)

    def temps(self) -> None:
        for path in _files(self.lib / TMP):
            age = self.now - _mtime(path)
            if age > STALE_TEMP_SECONDS:
                self.add("finding", "temp_stale", path)

    def modes(self) -> None:
        if not _POSIX:
            return
        private = [self.lib / INDEX_FILE, *_tree(self.lib / TMP), *_tree(self.root / SCRATCH)]
        private += _tree(self.root / LOGS)
        advisory = [*_tree(self.lib / OBJECTS), *_tree(self.lib / REFS)]
        classes: tuple[tuple[Level, list[Path]], ...] = (("finding", private), ("note", advisory))
        for level, paths in classes:
            for path in paths:
                if _open_mode(path):
                    self.add(level, "mode_open", path)

    def logs(self) -> None:
        for path in sorted((self.root / LOGS).glob("*.jsonl")):
            data = read_file(path) or b""
            log = None
            with contextlib.suppress(records.RecordError):
                log = records.read_job_log(data)
            if log is None:
                self.add("finding", "log_header_invalid", path)
                continue
            if log.bad_lines:
                self.add("finding", "log_bad_line", path)
            if log.truncated_tail:
                self.add("warning", "log_truncated", path)


def _object_files(objects: Path) -> Iterator[tuple[Path, str | None]]:
    """Every file under `objects/`, with its record id, or None for a name that is not one."""
    if not objects.is_dir():
        return
    for fan in sorted(objects.iterdir()):
        if not fan.is_dir() or fan.is_symlink():
            yield fan, None
            continue
        for path in sorted(fan.iterdir()):
            stem = path.name[: -len(_SUFFIX)] if path.name.endswith(_SUFFIX) else ""
            candidate = f"sha256:{fan.name}{stem}"
            ok = path.is_file() and record_digest(candidate) is not None
            yield path, candidate if ok else None


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []


def _tree(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return [folder, *sorted(folder.rglob("*"))]


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _open_mode(path: Path) -> bool:
    try:
        return bool(stat.S_IMODE(os.lstat(path).st_mode) & 0o077)
    except OSError:
        return False


def _indexed_ids(path: Path) -> tuple[int, set[str]] | None:
    """The index's schema version and ids, read-only; None when it is not a readable index."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != _index.SCHEMA_VERSION:
            return version, set()
        return version, {r[0] for r in conn.execute("SELECT id FROM records")}
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def check(
    root: Path,
    *,
    probe: Callable[[Path], str | None] | None = None,
    now: float | None = None,
) -> FsckReport:
    """Every finding for the library at `root`; read-only. `probe` is accepted for symmetry
    with `repair` and unused: a check needs no lock."""
    del probe
    walk = _Walk(root, time.time() if now is None else now)
    if not walk.lib.is_dir():
        return FsckReport((), 0)
    if not walk.layout_newer():
        walk.objects_and_links()
        walk.refs()
        walk.index()
        walk.temps()
        walk.modes()
        walk.logs()
    return FsckReport(tuple(walk.items), walk.objects)


def _quarantine(lib: Path, source: Path) -> None:
    """Copy `source` into `quarantine/` (atomic, create-once), then remove it."""
    data = read_file(source)
    if data is None:
        return
    folder = lib / QUARANTINE
    ensure_private_dir(folder)
    base = source.parent.name + source.name if source.parent.name != OBJECTS else "stray"
    if record_digest(f"sha256:{base[: -len(_SUFFIX)]}") is None:
        base = "stray"
    for n in range(1000):
        name = base if n == 0 else f"{base}.{n}"
        if write_once(folder, name, data, tmp_dir=lib / TMP) or read_file(folder / name) == data:
            source.unlink()
            return


def repair(
    root: Path,
    *,
    probe: Callable[[Path], str | None] | None = None,
    now: float | None = None,
) -> tuple[tuple[Action, ...], FsckReport]:
    """Apply the repairs plan 4.10 allows; return them and the report after them."""
    before = check(root, now=now)
    if any(f.code == "layout_newer" for f in before.items) or not (root / LIBRARY).is_dir():
        return (), before
    lib = root / LIBRARY
    ensure_private_dir(lib / TMP)
    actions: list[Action] = []
    for f in before.items:
        if f.code in _CORRUPT_CODES:
            _quarantine(lib, root / f.target)
            actions.append(Action("object_quarantined", f.target))
        elif f.code == "temp_stale":
            with contextlib.suppress(FileNotFoundError):
                (root / f.target).unlink()
            actions.append(Action("temp_deleted", f.target))
    library = open_library(root, probe=probe)
    if library.degraded is None:
        dangling = [
            root / f.target for f in before.items if f.code in ("ref_dangling", "ref_corrupt")
        ]
        removed = _refs.remove_refs(library, dangling)
        actions += [Action("ref_removed", p.relative_to(root).as_posix()) for p in removed]
        library.rebuild_index()
        actions.append(Action("index_rebuilt", f"{LIBRARY}/{INDEX_FILE}"))
    return tuple(actions), check(root, now=now)
