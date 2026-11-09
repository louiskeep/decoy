"""G-ONE-PRIVATE-FILE seeds for import aliases and staged-sink bindings.

Each case goes through the real `seeded` -> `run` -> `all_findings` path of
`test_private_files.py`. A sink, entry point or `suppress` is named by what its import resolves
to (`_calls.leaf`), so renaming it on import must not hide it from P1, P1b or P3; a `staged` row
holds only when the sink writes the temp a stager yields.
"""

from __future__ import annotations

import pytest
from tests.sentry.io_policy.test_private_files import (
    CHOKE_POINT,
    NEW,
    ROWS,
    SRC,
    STAGED_FILE,
    Row,
    _has,
    live_files,
    run,
    seeded,
)

_ALIASED_SINKS = [
    ("from io import open as io_open\ndef f(p):\n    io_open(p, 'wb')\n", "open"),
    (
        "from pyarrow.parquet import write_table as wt\ndef f(t, p):\n    wt(t, p)\n",
        "write_table",
    ),
    (
        "from decoy_engine import write_fixed_width as w\ndef f(t, lay, p):\n    w(t, lay, p)\n",
        "write_fixed_width",
    ),
    ("import tempfile as tf\ndef f():\n    return tf.mkdtemp()\n", "tempfile.mkdtemp"),
]


@pytest.mark.parametrize(("source", "kind"), _ALIASED_SINKS)
def test_an_import_alias_does_not_hide_a_raw_sink(source: str, kind: str) -> None:
    assert _has(seeded(source), "P1", "sink with no row", f"{NEW}::f::{kind}::1")


def test_an_import_alias_does_not_hide_a_private_entry_point() -> None:
    src = "from decoy._atomic import write_local_target as w\ndef f(p, d):\n    w(p, d, None)\n"
    assert _has(seeded(src), "P1b", "private site with no case", f"{NEW}::f::write_local_target::1")


def test_an_aliased_via_call_binds_a_private_row() -> None:
    src = (
        "from decoy._private_file import open_private as op\n"
        "def f(path):\n    op(path, new_parent=False)\n    open(path, 'wb')\n"
    )
    row = Row(
        NEW, "f", "open", 1, "private", "seeded row for the sentry's own test", "open_private"
    )
    findings = seeded(src, rows=[row])
    assert not _has(findings, "P2", f"{NEW}::f::open::1")


def test_an_aliased_suppress_is_a_swallowed_try() -> None:
    src = (
        "import os\nfrom contextlib import suppress as quiet\n"
        "def f(fd):\n    with quiet(OSError):\n        os.fchmod(fd, 0o600)\n"
    )
    assert _has(seeded(src), "P3", f"{NEW}::f::os.fchmod::1")


def test_an_aliased_suppress_in_the_choke_point_is_red() -> None:
    live = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    extra = (
        "\n\ndef _seeded(fd):\n    from contextlib import suppress as quiet\n"
        "    with quiet(OSError):\n        os.fchmod(fd, 0o600)\n"
    )
    findings = run({**live_files(), CHOKE_POINT: live + extra})
    assert _has(findings, "P3", f"{CHOKE_POINT}::_seeded::os.fchmod::1")


def test_a_non_contextlib_suppress_is_not_blamed() -> None:
    src = (
        "import os\nfrom mylib import suppress\n"
        "def f(fd):\n    with suppress(OSError):\n        os.fchmod(fd, 0o600)\n"
    )
    assert not _has(seeded(src), "P3")


_STAGE = "    with stage(path) as tmp:"


def _targets_with(extra: str) -> dict[str, str]:
    files = live_files()
    assert files[STAGED_FILE].count(_STAGE) == 1
    return {**files, STAGED_FILE: files[STAGED_FILE].replace(_STAGE, extra + _STAGE)}


@pytest.mark.parametrize(
    "extra",
    [
        '    path.write_text("PRIVATE VALUE")\n',
        '    path.write_bytes(b"PRIVATE VALUE")\n',
    ],
)
def test_a_staged_row_for_a_sink_that_writes_the_final_path_is_red(extra: str) -> None:
    kind = "write_text" if "write_text" in extra else "write_bytes"
    row = Row(STAGED_FILE, "_write_table", kind, 1, "staged", "seeded row, exact key and file")
    findings = run(_targets_with(extra), rows=[*ROWS, row])
    assert _has(findings, "P1", "staged sink does not write", row.key)
    assert not _has(findings, "sink with no row")


def test_the_live_staged_rows_all_write_their_stage_temp() -> None:
    assert not _has(run(live_files()), "staged sink does not write")
