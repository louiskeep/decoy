"""The one rule for a file name a user chooses (a table name that becomes a file name)."""

from __future__ import annotations

from decoy._atomic import is_device_name


def is_portable_component(name: object) -> bool:
    """True when a user-chosen `name` is one file name that is safe on every OS.

    Not empty, not `.` or `..`, no separator (`/` or `\\`), no NUL, no `:` (a Windows drive or
    stream), and not a Windows device name. This is the one rule for a name a user picks (a
    table name that becomes a file name). Internal names with a stricter alphabet keep their own
    entry points (`decoy._atomic` writes, `is_valid_name` for pipelines).
    """
    return (
        isinstance(name, str)
        and name not in ("", ".", "..")
        and not any(char in name for char in ("/", "\\", "\x00", ":"))
        and not is_device_name(name)
    )
