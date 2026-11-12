"""Turn what a user typed into one record id (plan 4.5): an id, a prefix, a ref, or `latest`.

- `sha256:<64 hex>` or any unique prefix of 8 or more hex digits, with or without `sha256:`, as
  git allows abbreviated object names; several matches are refused, never the first taken.
- `<kind>/<name>` or `<kind>/<scope>/<name>`: a stored ref.
- `<kind>/latest` and `<kind>/latest~N`: the newest record of that kind by `(created_at, id)`,
  and the N-th before it (git's `HEAD~N`); computed from the index, never stored.

Messages name the problem, never the typed text.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from decoy.cli.library._errors import LibraryError
from decoy.cli.library._refs import LATEST

if TYPE_CHECKING:
    from decoy.cli.library._store import Library

__all__ = ["TargetError", "resolve_target"]

_LATEST = re.compile(rf"{LATEST}(?:~([0-9]{{1,6}}))?")
_HEX = frozenset("0123456789abcdef")
_MIN_PREFIX = 8


class TargetError(Exception):
    """The text names no record, or more than one."""


def resolve_target(library: Library, text: str) -> str:
    """The one record id `text` names. Raises `TargetError`."""
    if "/" in text:
        kind, _, name = text.partition("/")
        found = _LATEST.fullmatch(name)
        if found is not None:
            return _latest(library, kind, int(found.group(1) or 0))
        code: str | None = None
        rid: str | None = None
        try:
            rid = library.read_ref(kind, name)
        except LibraryError as exc:
            code = exc.code
        if code is not None:
            raise TargetError(f"not a ref name ({code})")
        if rid is None:
            raise TargetError("no ref of that name is set")
        return rid
    digest = text.removeprefix("sha256:")
    if not (_MIN_PREFIX <= len(digest) <= 64 and set(digest) <= _HEX):
        raise TargetError("an id or prefix needs 8 to 64 lower-case hex digits")
    matches = library.resolve(text)
    if not matches:
        raise TargetError("no record has that id")
    if len(matches) > 1:
        raise TargetError(f"ambiguous id prefix: {len(matches)} records match; give more digits")
    return matches[0]


def _latest(library: Library, kind: str, back: int) -> str:
    rows = library.rows(kind=kind)
    if back >= len(rows):
        raise TargetError(f"{len(rows)} record(s) of that kind; {LATEST}~{back} does not exist")
    return rows[-1 - back].id
