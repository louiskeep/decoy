"""The local record library: one store of value-free records per project (LIB plan, L1b.2).

Commands import this facade, never a `_` module (G-LIB-WRITER). What exists so far: the root
rule (`resolve_root`), the store (`open_library`, `Library.put`, `resolve`) and the error
type. Reading records back, refs, the index, scratch and logs arrive in later slices. See docs/library.md.
"""

from __future__ import annotations

from decoy.cli.library._errors import LibraryError
from decoy.cli.library._paths import LibraryRoot, resolve_root
from decoy.cli.library._store import Library, PutResult, open_library

__all__ = [
    "Library",
    "LibraryError",
    "LibraryRoot",
    "PutResult",
    "open_library",
    "resolve_root",
]
