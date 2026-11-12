"""The record store: `put`, `get`, `resolve` and the ref entry points over content-addressed object files.

The shape is git's object store: immutable objects named by their content hash under a two-hex
fan-out (`objects/ab/<62 hex>.json`), written to a temp file and moved into place without ever
replacing a file. An existing object is success only when it passes the one id rule
(`decoy_engine.records.record_id`, which `records.decode` also applies: parse, drop `id`,
canonicalize, hash), so a CRLF checkout of a valid record is fine and a different file under the
same name is `record_corrupt` (plan 4.3, 4.8). A record may only link to records already stored
(plan 4.3): ids hash their links, so the link graph has no cycles by construction. Record writes
take no lock (plan 4.8); the index row is inserted only after the object exists, and a failed
insert never fails the put (the next locked open catches up, plan 4.4).

`open_library` probes for a network filesystem and runs the index freshness sync once. A remote
root or an index that cannot be locked puts the library in degraded mode (plan 4.8): `put` still
works, ref updates refuse with `library_lock_unavailable`, and queries parse the object files.

`put` is the only writer under `library/objects/` and `records.encode` is called only here
(G-LIB-WRITER, tests/sentry/io_policy/test_library_writer.py). Plan sections 4.2, 4.3, 4.5, 4.8
and 4.9 of `plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from decoy_engine import records

from decoy.cli.io import LayoutWarning, ensure_decoy_dir
from decoy.cli.library import _index
from decoy.cli.library._errors import (
    LIBRARY_LAYOUT_NEWER,
    LIBRARY_LOCK_UNAVAILABLE,
    LIBRARY_READ_FAILED,
    LIBRARY_WRITE_FAILED,
    RECORD_CORRUPT,
    RECORD_INVALID,
    RECORD_LINK_MISSING,
    RECORD_NOT_FOUND,
    LibraryError,
    library_error,
)
from decoy.cli.library._fs import ensure_private_dir, read_file, write_dotfile_once, write_once
from decoy.cli.library._index import IndexRow
from decoy.cli.library._paths import (
    GITATTRIBUTES,
    GITATTRIBUTES_TEXT,
    LAYOUT_FILE,
    LAYOUT_VERSION,
    LIBRARY,
    OBJECTS,
    SCRATCH,
    TMP,
    check_root_budget,
    is_project_folder,
    record_digest,
)
from decoy.cli.library._refs import read_ref, set_ref
from decoy.cli.library._remote import remote_filesystem
from decoy.cli.library._scratch import DeleteReport, ScratchAllocation, allocate, delete_tree

__all__ = ["Library", "PutResult", "open_library"]

_PREFIX = "sha256:"
_HEX = frozenset("0123456789abcdef")
_DIGEST_CHARS = 64  # a full id; `record_digest` checks one
_MIN_PREFIX = 8  # as git allows abbreviated object names
_SUFFIX = ".json"

Decoded = records.DecodedRecord | records.OpaqueRecord | records.RecordNeedsNewer
Probe = Callable[[Path], "str | None"]
REMOTE_FILESYSTEM = "remote_filesystem"
LOCK_UNAVAILABLE = "lock_unavailable"


@dataclass(frozen=True)
class PutResult:
    """`created` is False when the record was already stored (the same id is the same bytes).
    `warnings` are project-layout warnings from the first write (a `.gitignore` it could not
    write)."""

    id: str
    created: bool
    warnings: tuple[LayoutWarning, ...] = ()


class Library:
    """One library root. Build it with `open_library`; setup runs once, on the first `put`.

    `degraded` is None, `"remote_filesystem"` (with `filesystem` naming it) or
    `"lock_unavailable"`. `stale` is True when the index could not be caught up this time (the
    lock was busy); queries then read the object files.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._library = root / LIBRARY
        self._objects = self._library / OBJECTS
        self._tmp = self._library / TMP
        self._ready = False
        self.degraded: str | None = None
        self.filesystem: str | None = None
        self.stale = False

    def _open(self, probe: Probe) -> None:
        self.filesystem = probe(self.root)
        if self.filesystem is not None:
            self.degraded = REMOTE_FILESYSTEM
        elif self._library.is_dir():
            self._catch_up()

    def _catch_up(self) -> None:
        """The freshness sync under the lock (plan 4.4); a missing or corrupt index is rebuilt."""
        code: str | None = None
        try:
            with _index.locked(self._library, tmp_dir=self._tmp) as conn:
                _index.ensure_schema(conn)
                _index.sync(conn, _index.object_ids(self._objects), self._index_row)
        except LibraryError as exc:
            code = exc.code
        if code == LIBRARY_LOCK_UNAVAILABLE:
            self.degraded = LOCK_UNAVAILABLE
        elif code is not None:
            self.stale = True

    def object_path(self, record_id: str) -> Path | None:
        """Where the object file for this full id lives (whether or not it exists)."""
        digest = record_digest(record_id)
        return None if digest is None else self._object(digest)

    def index_row(self, record_id: str) -> IndexRow | None:
        """The index row for a stored object, read from its file (see `_index_row`)."""
        return self._index_row(record_id)

    def _index_row(self, record_id: str) -> IndexRow | None:
        """The row for a stored object, or None when it is corrupt or of an unreadable major
        (fsck reports those)."""
        try:
            decoded = self.get(record_id)
        except LibraryError:
            return None
        if isinstance(decoded, records.RecordNeedsNewer) and not decoded.verified:
            return None
        digest = record_digest(record_id) or ""
        size = os.stat(self._object(digest)).st_size
        return _index.row_from(decoded.raw, size, isinstance(decoded, records.DecodedRecord))

    def _index_put(self, row: IndexRow) -> None:
        if self.degraded is not None:
            return
        try:
            with _index.locked(self._library, tmp_dir=self._tmp) as conn:
                _index.ensure_schema(conn)
                _index.insert(conn, row)
        except LibraryError:
            self.stale = True  # the object is stored; the next locked open inserts the row

    def scratch(
        self, owner: str, invocation_id: str, *, ttl: timedelta | None = None
    ) -> AbstractContextManager[ScratchAllocation]:
        """A protected scratch allocation for rows (plan 4.6, 4.7), from the engine allocator.

        With no `ttl` it is staging, removed when the block exits on success or error, with
        files another program holds open reported in `.report` and left for a later cleanup.
        With a `ttl` it is kept under `scratch/<owner>-<invocation_id>` (sample output). Raises
        `LibraryError` (`scratch_acl_failed`, `scratch_unsafe`) before the block runs, leaving
        no directory, or `ValueError` for an owner outside `[a-z0-9][a-z0-9-]{0,31}`.
        """
        return allocate(self, owner, invocation_id, ttl)

    def delete_scratch(self, path: Path) -> DeleteReport:
        """Best-effort delete of a folder inside `scratch/`; held-open files are reported."""
        scratch = (self.root / SCRATCH).resolve()
        target = path.resolve()
        if scratch not in target.parents:
            raise ValueError("only a folder inside scratch/ can be deleted here")
        return delete_tree(target)

    def has(self, record_id: str) -> bool:
        """Whether an object file exists for this full id (no read)."""
        digest = record_digest(record_id)
        return digest is not None and self._object(digest).is_file()

    def rebuild_index(self) -> None:
        """Drop the index and rebuild it from the object files, under the lock (fsck --repair).
        Raises `LibraryError` when the lock cannot be taken."""
        with _index.locked(self._library, tmp_dir=self._tmp) as conn:
            _index.rebuild(conn)
            _index.sync(conn, _index.object_ids(self._objects), self._index_row)
        self.stale = False

    def rows(
        self, *, kind: str | None = None, pipeline: str | None = None, table: str | None = None
    ) -> list[IndexRow]:
        """Rows matching the filters, oldest first. From the index; when the library is
        degraded or the index is stale, from the object files."""
        return _index.select(self._all_rows(), kind=kind, pipeline=pipeline, table=table)

    def latest(
        self, kind: str, *, pipeline: str | None = None, table: str | None = None
    ) -> str | None:
        """The virtual `latest` (plan 4.5): the largest `(created_at, id)` of `kind`."""
        return _index.latest(self._all_rows(), kind=kind, pipeline=pipeline, table=table)

    def _all_rows(self) -> list[IndexRow]:
        if not self._library.is_dir():
            return []
        if self.degraded is None and not self.stale:
            rows: list[IndexRow] | None = None
            try:
                with _index.locked(self._library, tmp_dir=self._tmp) as conn:
                    _index.ensure_schema(conn)
                    rows = _index.all_rows(conn)
            except LibraryError:
                rows = None
            if rows is not None:
                return rows
        loaded = (self._index_row(i) for i in sorted(_index.object_ids(self._objects)))
        return [row for row in loaded if row is not None]

    def _object(self, digest: str) -> Path:
        return self._objects / digest[:2] / f"{digest[2:]}{_SUFFIX}"

    def put(self, envelope: records.RecordEnvelope) -> PutResult:
        """Store a built envelope; storing it again is success. Raises `LibraryError`."""
        digest = (
            record_digest(envelope.id) if isinstance(envelope, records.RecordEnvelope) else None
        )
        if digest is None:
            raise LibraryError(RECORD_INVALID)
        for link in envelope.links:
            target = record_digest(link.id)
            if target is None or not self._object(target).is_file():
                raise LibraryError(RECORD_LINK_MISSING)
        warnings = self.prepare()
        data = records.encode(envelope)
        folder = self._objects / digest[:2]
        ensure_private_dir(folder)
        created = write_once(folder, f"{digest[2:]}{_SUFFIX}", data, tmp_dir=self._tmp)
        if not created:
            self._verify(self._object(digest), envelope.id)
        self._index_put(_index.row_from(envelope.to_dict(), len(data), True))
        return PutResult(envelope.id, created, warnings)

    def get(self, record_id: str) -> Decoded:
        """The verified record stored under this full id. Raises `LibraryError`:
        `record_not_found`, `record_corrupt` (the content is not this record) or the engine's
        `record_invalid` (a payload its read model refuses).

        `records.decode` applies the one id rule and returns the typed view with the raw
        envelope, an `OpaqueRecord` for a kind this version does not know, or
        `RecordNeedsNewer`. This is the one library read (G-ONE-SCAN-READER exempts this file).
        """
        digest = record_digest(record_id)
        data = None if digest is None else read_file(self._object(digest))
        if data is None:
            raise LibraryError(RECORD_NOT_FOUND)
        failure: records.RecordError | None = None
        decoded: Decoded | None = None
        try:
            decoded = records.decode(data)
        except records.RecordError as exc:
            failure = exc
        if failure is not None:
            raise library_error(failure.code, failure)
        if decoded is None or decoded.id != record_id or not getattr(decoded, "verified", True):
            raise LibraryError(RECORD_CORRUPT)
        return decoded

    def resolve(self, text: str) -> tuple[str, ...]:
        """Every stored id that `text` (a full id, or 8 or more hex digits) is a prefix of.

        Empty for no match or for text that is not a prefix; more than one means ambiguous.
        """
        digest = text.removeprefix(_PREFIX)
        if not (_MIN_PREFIX <= len(digest) <= _DIGEST_CHARS and set(digest) <= _HEX):
            return ()
        failure: OSError | None = None
        names: list[str] = []
        try:
            names = os.listdir(self._objects / digest[:2])
        except FileNotFoundError:
            return ()
        except OSError as exc:
            failure = exc
        if failure is not None:
            raise library_error(LIBRARY_READ_FAILED, failure)
        rest = digest[2:]
        return tuple(
            sorted(
                f"{_PREFIX}{digest[:2]}{name.removesuffix(_SUFFIX)}"
                for name in names
                if name.endswith(_SUFFIX)
                and name.startswith(rest)
                and record_digest(f"{_PREFIX}{digest[:2]}{name.removesuffix(_SUFFIX)}") is not None
            )
        )

    @property
    def library_dir(self) -> Path:
        return self._library

    @property
    def tmp_dir(self) -> Path:
        return self._tmp

    def set_ref(self, kind: str, name: str, record_id: str) -> None:
        """Point `refs/<kind>/<name>` at a stored record, under the library lock (plan 4.5)."""
        set_ref(self, kind, name, record_id)

    def read_ref(self, kind: str, name: str) -> str | None:
        """The record id `refs/<kind>/<name>` holds, or None when the ref is not set."""
        return read_ref(self, kind, name)

    def prepare(self) -> tuple[LayoutWarning, ...]:
        """Make the root, its git files, `library/`, `tmp/`, `LAYOUT` and `objects/`, once."""
        if self._ready:
            return ()
        warnings: tuple[LayoutWarning, ...] = ()
        ensure_private_dir(self.root)
        if is_project_folder(self.root):
            failure: OSError | None = None
            try:
                warnings = ensure_decoy_dir(self.root.parent)
            except OSError as exc:
                failure = exc
            if failure is not None:
                raise library_error(LIBRARY_WRITE_FAILED, failure)
            write_dotfile_once(self.root / GITATTRIBUTES, GITATTRIBUTES_TEXT.encode("utf-8"))
        ensure_private_dir(self._library)
        ensure_private_dir(self._tmp)
        self._check_layout()
        ensure_private_dir(self._objects)
        self._ready = True
        return warnings

    def _check_layout(self) -> None:
        """Write `LAYOUT` once; refuse a library whose layout this version does not write."""
        layout = records.canonical_bytes({"layout": LAYOUT_VERSION})
        if write_once(self._library, LAYOUT_FILE, layout, tmp_dir=self._tmp):
            return
        found: object = None
        try:
            found = json.loads(read_file(self._library / LAYOUT_FILE) or b"null")
        except ValueError:
            found = None
        version = found.get("layout") if isinstance(found, dict) else None
        if version != LAYOUT_VERSION or isinstance(version, bool):
            raise LibraryError(LIBRARY_LAYOUT_NEWER)

    @staticmethod
    def _verify(path: Path, record_id: str) -> None:
        """An existing object is the same record only if its parsed content has this id.

        Parsing first means a CRLF or re-indented copy keeps its id. Only the id is checked: a
        record of a kind or major this version cannot read is still the same bytes.
        """
        data = read_file(path)
        parsed: object = None
        try:
            parsed = json.loads(data) if data is not None else None
        except ValueError:
            parsed = None
        same = False
        if isinstance(parsed, dict) and parsed.get("id") == record_id:
            try:
                same = records.record_id(parsed) == record_id
            except (TypeError, ValueError):  # NaN, or a value JSON cannot hold
                same = False
        if not same:
            raise LibraryError(RECORD_CORRUPT)


def open_library(root: Path, *, probe: Probe | None = None) -> Library:
    """The library at `root` (from `resolve_root`). Checks the Windows path budget, probes for a
    network filesystem (`probe`, default `_remote.remote_filesystem`) and, when the library
    exists, catches the index up with the object files. Creates nothing for a new library until
    the first `put`."""
    check_root_budget(root)
    library = Library(root)
    library._open(probe or remote_filesystem)
    return library
