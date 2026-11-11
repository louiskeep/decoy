"""The local record library: one store of value-free records per project (LIB plan, L1b, L1c).

Commands import this facade, never a `_` module (G-LIB-WRITER). What exists so far: the root
rule (`resolve_root`), the store (`open_library`, `Library.put`, `get`, `resolve`, `rows`,
`latest`), refs (`Library.set_ref`, `read_ref`, under the library lock), the index and degraded
mode, the retention policy model (`load_policy`), the error type, and the `library` command group
(`library_app`: `path`, `fsck`). Scratch and logs arrive in later slices. See docs/library.md.

Only `library_app` is imported eagerly; every other name loads on first use (PEP 562), so
registering the group keeps the record engine out of `decoy --help` and `--version`.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from decoy.cli.library._commands import library_app

if TYPE_CHECKING:
    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._paths import LibraryRoot, resolve_root
    from decoy.cli.library._policy import LibraryPolicy, load_policy
    from decoy.cli.library._store import Library, PutResult, open_library

__all__ = [
    "Library",
    "LibraryError",
    "LibraryPolicy",
    "LibraryRoot",
    "PutResult",
    "library_app",
    "load_policy",
    "open_library",
    "resolve_root",
]

_LAZY = {
    "Library": "_store",
    "LibraryError": "_errors",
    "LibraryPolicy": "_policy",
    "LibraryRoot": "_paths",
    "PutResult": "_store",
    "load_policy": "_policy",
    "open_library": "_store",
    "resolve_root": "_paths",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(importlib.import_module(f"decoy.cli.library.{module}"), name)
