"""Sentry: the two layout helpers vendored from the engine are pinned by digest.

``_layout.py`` and ``_ratchet_cases.py`` are byte-for-byte copies of the engine's files at
engine main commit ``426e6d057e6c087c902d814bd580a4976d789f77`` (first vendored at LAYOUT E2). ``PINS`` holds the same digests
as the engine's own ``test_vendored_files.py``, and the ``ci/vendored.toml`` rows for both files
must agree with them, so the cross-repository byte check in ``test_ci_lock_installs.py`` covers
them too. Changing a helper means landing it in the engine first, then re-vendoring here and
updating both the pins and the ledger rows.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

LAYOUT = Path(__file__).resolve().parent
ROOT = LAYOUT.parents[2]
ENGINE_COMMIT = "426e6d057e6c087c902d814bd580a4976d789f77"

PINS: dict[str, str] = {
    "_layout.py": "090676684a73bc90bb73240b1a3909434cd15ed8348c15bc365b7d764d94e96c",
    "_ratchet_cases.py": "038d0dff5e370a8238712c365db283b9befefc40135956dc61f05930946bab00",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin_findings(folder: Path) -> list[str]:
    return [
        f"{name} changed: re-vendor it from the engine and update PINS"
        for name, pinned in PINS.items()
        if digest((folder / name).read_bytes()) != pinned
    ]


def test_vendored_helpers_match_their_pins() -> None:
    assert pin_findings(LAYOUT) == []


def test_the_ledger_rows_agree_with_the_pins() -> None:
    ledger = tomllib.loads((ROOT / "ci" / "vendored.toml").read_text(encoding="utf-8"))
    rows = {
        v["local_path"]: v
        for v in ledger["vendored"]
        if v["local_path"].startswith("tests/sentry/layout/")
    }
    assert set(rows) == {f"tests/sentry/layout/{name}" for name in PINS}
    for name, pinned in PINS.items():
        row = rows[f"tests/sentry/layout/{name}"]
        assert row["engine_path"] == row["local_path"]
        assert (row["blob_sha256"], row["commit"]) == (pinned, ENGINE_COMMIT)


def test_one_changed_byte_in_either_helper_is_red(tmp_path: Path) -> None:
    for changed in PINS:
        for name in PINS:
            data = (LAYOUT / name).read_bytes()
            (tmp_path / name).write_bytes(data + b" " if name == changed else data)
        assert pin_findings(tmp_path) == [
            f"{changed} changed: re-vendor it from the engine and update PINS"
        ]
