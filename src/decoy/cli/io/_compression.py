"""Compression by file name, for CSV targets the CLI writes.

pandas picks a CSV codec from the path's suffix. A staged write goes to a temp name that
ends in `.tmp`, so the codec has to be named from the real target instead. This module is
the one table of suffixes (the same set pandas infers, `.tgz` is not one of them) and the
one place that builds the `compression=` option. It holds no table write call.

Source pattern: `pandas.io.common.extension_to_compression` for the suffix set, and the
`compression` dict of `DataFrame.to_csv` (`method`, `archive_name`, `mode`).
"""

from __future__ import annotations

from pathlib import Path

# Longest suffix first, so `.tar.gz` is matched before `.gz`. Same set pandas infers.
COMPRESSION = (
    (".tar.bz2", "tar"),
    (".tar.gz", "tar"),
    (".tar.xz", "tar"),
    (".bz2", "bz2"),
    (".tar", "tar"),
    (".zip", "zip"),
    (".zst", "zstd"),
    (".gz", "gzip"),
    (".xz", "xz"),
)
ARCHIVES = ("zip", "tar")


def split_compression(path: Path) -> tuple[str, str | None]:
    """Return the file name without one recognised compression suffix, and its method."""
    name = path.name.lower()
    for suffix, method in COMPRESSION:
        if name.endswith(suffix):
            return name[: -len(suffix)], method
    return name, None


def is_archive_csv(fmt: str, path: Path) -> bool:
    return fmt == "csv" and split_compression(path)[1] in ARCHIVES


def csv_compression(path: Path) -> str | dict[str, str] | None:
    """The `to_csv(compression=...)` option the real target name implies, else None.

    A stream codec is a method string. An archive (zip, tar) also names its one member after
    the real file with the archive suffix cut (`out.csv.zip` holds `out.csv`), never after the
    staging name. A compressed tar says its tar mode, because pandas reads that from the
    written file's own suffix and the staging file has none.
    """
    name = path.name
    for suffix, method in COMPRESSION:
        if not name.lower().endswith(suffix):
            continue
        if method not in ARCHIVES:
            return method
        option = {"method": method, "archive_name": name[: -len(suffix)]}
        if method == "tar":
            option["mode"] = "w:" + suffix.rsplit(".", 1)[1] if suffix != ".tar" else "w"
        return option
    return None
