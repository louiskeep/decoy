"""The library's failure type and its one builder, `library_error`: a code plus a class name.

Every library failure is rendered as `code (ErrorClass)` and nothing else: an `OSError` text
names the path, and a path can name a user or a host, so it never reaches `str(exc)` (the engine
`write_private` rule, plan 4.9 step 5). The builder is called after the `except` block closes,
so no `OSError` is chained as `__cause__` or `__context__`.

Codes the engine registry holds are imported from `decoy_engine.reasons`, never copied
(tests/sentry/test_engine_reason_code_copies.py). The library-only codes below are CLI constants
(re-FRAME owner answer Q4): they are printed, never written into a job-log event.
"""

from __future__ import annotations

from decoy_engine.reasons import runtime, warning

__all__ = [
    "LIBRARY_BUSY",
    "LIBRARY_FILE_TOO_LARGE",
    "LIBRARY_LAYOUT_NEWER",
    "LIBRARY_LOCK_UNAVAILABLE",
    "LIBRARY_PATH_TOO_LONG",
    "LIBRARY_READ_FAILED",
    "LIBRARY_WRITE_FAILED",
    "RECORD_CORRUPT",
    "RECORD_INVALID",
    "RECORD_LINK_MISSING",
    "RECORD_NOT_FOUND",
    "LibraryError",
    "library_error",
]

RECORD_CORRUPT = runtime.RECORD_CORRUPT
RECORD_INVALID = runtime.RECORD_INVALID
LIBRARY_WRITE_FAILED = warning.LIBRARY_WRITE_FAILED

LIBRARY_BUSY = "library_busy"
LIBRARY_LOCK_UNAVAILABLE = "library_lock_unavailable"
LIBRARY_PATH_TOO_LONG = "library_path_too_long"
LIBRARY_LAYOUT_NEWER = "library_layout_newer"
RECORD_LINK_MISSING = "record_link_missing"
RECORD_NOT_FOUND = "record_not_found"
# An object file exists but cannot be read (permissions, I/O error); not corruption.
LIBRARY_READ_FAILED = "library_read_failed"
# A library file larger than its cap: refused unread, so a planted huge file cannot exhaust memory.
LIBRARY_FILE_TOO_LARGE = "library_file_too_large"


class LibraryError(Exception):
    """A library operation failed. `code` is one of the constants above; `error_class` names the
    underlying exception's class, or is empty when there was none."""

    def __init__(self, code: str, error_class: str = "") -> None:
        super().__init__(f"{code} ({error_class})" if error_class else code)
        self.code = code
        self.error_class = error_class


def library_error(code: str, exc: BaseException | None = None) -> LibraryError:
    """The one builder: the code and, when given, the class name of `exc`; never its text."""
    return LibraryError(code, type(exc).__name__ if exc is not None else "")
