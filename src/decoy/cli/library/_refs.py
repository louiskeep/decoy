"""Named refs (plan 4.5, 4.8; L1b.3).

A ref is git's named ref: a small file `library/refs/<kind>/<name>` holding one record id and a
newline. It is replaced in one step through `_atomic` (`REPLACE`, which retries a held-open
target on Windows), so a reader sees the old id or the new one. Refs are the roots prune keeps.

Every ref update runs under the library lock, `_index.locked` (`BEGIN IMMEDIATE` on
`library/index.sqlite`, pre-created 0600; the one open and lock mechanism the index uses too).
A waiter gives up with `library_busy` and never overwrites; a lock that cannot be taken, or a
library in degraded mode (a network filesystem, plan 4.8), is `library_lock_unavailable`. The
target's existence is checked under the lock, so a later prune (which takes the same lock)
cannot remove it in between.

`latest` is virtual and computed from the index (`Library.latest`); it is not a stored ref.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from decoy_engine import records

from decoy.cli.library import _index
from decoy.cli.library._errors import (
    LIBRARY_LOCK_UNAVAILABLE,
    RECORD_CORRUPT,
    REF_NAME_INVALID,
    REF_NAME_RESERVED,
    LibraryError,
)
from decoy.cli.library._fs import ensure_private_dir, read_capped, replace_file
from decoy.cli.library._paths import REFS, record_digest

if TYPE_CHECKING:
    from decoy.cli.library._store import Library

__all__ = ["read_ref", "set_ref"]

# "sha256:" + 64 hex + a newline is 72 bytes; the rest is slack for a CRLF or editor newline.
_MAX_REF_BYTES = 128
# One-part names that are a scope for two-part refs (plan 4.5: `scan-set/baseline/<slug>`); as a
# file they would collide with that folder.
_RESERVED_NAMES = frozenset({"baseline"})
# One name segment (plan 4.5); a name may hold two, `<scope>/<name>`, for a pipeline scope.
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_MAX_SEGMENTS = 2


def _ref_parts(kind: str, name: str) -> tuple[str, ...]:
    """The path parts under `refs/`; `ref_name_invalid` for anything outside the grammar and
    `ref_name_reserved` for a one-part name that is a scope."""
    kinds = {spec.kind for spec in records.registered_kinds()}
    parts = name.split("/")
    ok = (
        kind in kinds
        and len(parts) <= _MAX_SEGMENTS
        and all(_SEGMENT.fullmatch(part) for part in parts)
    )
    if not ok:
        raise LibraryError(REF_NAME_INVALID)
    if len(parts) == 1 and parts[0] in _RESERVED_NAMES:
        raise LibraryError(REF_NAME_RESERVED)
    return (kind, *parts)


def set_ref(library: Library, kind: str, name: str, record_id: str) -> None:
    """Point the ref at `record_id`, which must be stored. Raises `LibraryError`:
    `ref_name_invalid`, `ref_name_reserved`, `record_not_found`, `record_corrupt`, `library_busy`,
    `library_lock_unavailable` or `library_write_failed`."""
    parts = _ref_parts(kind, name)
    if library.degraded is not None:
        raise LibraryError(LIBRARY_LOCK_UNAVAILABLE)  # a remote or unlockable library (plan 4.8)
    library.prepare()
    with _index.locked(library.library_dir):
        library.get(record_id)  # exists and is the record its id names
        folder = library.library_dir / REFS
        ensure_private_dir(folder)
        for part in parts[:-1]:
            folder = folder / part
            ensure_private_dir(folder)
        replace_file(folder, parts[-1], f"{record_id}\n".encode(), tmp_dir=library.tmp_dir)


def read_ref(library: Library, kind: str, name: str) -> str | None:
    """The id the ref holds, or None when it is not set. A ref file is replaced in one step, so
    it is read without the lock. A file that holds no record id is `record_corrupt`."""
    path = library.library_dir / REFS
    for part in _ref_parts(kind, name):
        path = path / part
    data = read_capped(path, _MAX_REF_BYTES)
    if data is None:
        return None
    text = data.decode("utf-8", errors="replace").strip()
    if record_digest(text) is None:
        raise LibraryError(RECORD_CORRUPT)
    return text
