"""The record store: `put`, `get`, `resolve` and the ref entry points over content-addressed object files.

The shape is git's object store: immutable objects named by their content hash under a two-hex
fan-out (`objects/ab/<62 hex>.json`), written to a temp file and moved into place without ever
replacing a file. An existing object is success only when it passes the one id rule
(`decoy_engine.records.record_id`, which `records.decode` also applies: parse, drop `id`,
canonicalize, hash), so a CRLF checkout of a
valid record is fine and a different file under the same name is `record_corrupt` (plan 4.3,
4.8). A record may only link to records already stored (plan 4.3): ids hash their links, so the
link graph has no cycles by construction. Record writes take no lock (plan 4.8).

`put` is the only writer under `library/objects/` and `records.encode` is called only here
(G-LIB-WRITER, tests/sentry/io_policy/test_library_writer.py). Plan sections 4.2, 4.3, 4.5, 4.8
and 4.9 of `plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from decoy_engine import records

from decoy.cli.io import LayoutWarning, ensure_decoy_dir
from decoy.cli.library._errors import (
    LIBRARY_FILE_TOO_LARGE,
    LIBRARY_LAYOUT_NEWER,
    LIBRARY_READ_FAILED,
    LIBRARY_WRITE_FAILED,
    RECORD_CORRUPT,
    RECORD_INVALID,
    RECORD_LINK_MISSING,
    RECORD_NOT_FOUND,
    LibraryError,
    library_error,
)
from decoy.cli.library._fs import ensure_private_dir, read_capped, write_dotfile_once, write_once
from decoy.cli.library._paths import (
    GITATTRIBUTES,
    GITATTRIBUTES_TEXT,
    ID_PREFIX,
    LAYOUT_FILE,
    LAYOUT_VERSION,
    LIBRARY,
    OBJECTS,
    TMP,
    check_root_budget,
    is_project_folder,
    record_digest,
    record_prefix,
)
from decoy.cli.library._refs import read_ref, set_ref

__all__ = ["Library", "PutResult", "open_library"]

_SUFFIX = ".json"
# Records hold names, counts and digests only; 16 MiB is far above any real one and keeps a
# planted file from being read whole. `put` refuses a record it could not read back.
MAX_RECORD_BYTES = 16 * 1024 * 1024
_MAX_LAYOUT_BYTES = 4096

Decoded = records.DecodedRecord | records.OpaqueRecord | records.RecordNeedsNewer


@dataclass(frozen=True)
class PutResult:
    """`created` is False when the record was already stored (the same id is the same bytes).
    `warnings` are project-layout warnings from the first write (a `.gitignore` it could not
    write)."""

    id: str
    created: bool
    warnings: tuple[LayoutWarning, ...] = ()


class Library:
    """One library root. Build it with `open_library`; setup runs once, on the first `put`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._library = root / LIBRARY
        self._objects = self._library / OBJECTS
        self._tmp = self._library / TMP
        self._ready = False

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
        if len(data) > MAX_RECORD_BYTES:
            raise LibraryError(LIBRARY_FILE_TOO_LARGE)
        folder = self._objects / digest[:2]
        ensure_private_dir(folder)
        created = write_once(folder, f"{digest[2:]}{_SUFFIX}", data, tmp_dir=self._tmp)
        if not created:
            self._verify(self._object(digest), envelope.id)
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
        data = None if digest is None else read_capped(self._object(digest), MAX_RECORD_BYTES)
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
        digest = record_prefix(text)
        if digest is None:
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
        found = (f"{ID_PREFIX}{digest[:2]}{name.removesuffix(_SUFFIX)}" for name in names)
        return tuple(
            sorted(
                record_id
                for record_id, name in zip(found, names)
                if name.endswith(_SUFFIX)
                and name.startswith(rest)
                and record_digest(record_id) is not None
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
            found = json.loads(
                read_capped(self._library / LAYOUT_FILE, _MAX_LAYOUT_BYTES) or b"null"
            )
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
        data = read_capped(path, MAX_RECORD_BYTES)
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


def open_library(root: Path) -> Library:
    """The library at `root` (from `resolve_root`). Checks the Windows path budget; writes
    nothing until the first `put`."""
    check_root_budget(root)
    return Library(root)
