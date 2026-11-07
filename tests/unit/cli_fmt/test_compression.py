"""CSV compression is named from the real target, not the staging temp (slice ATOMIC-OUTPUT)."""

from __future__ import annotations

import bz2
import gzip
import io
import tarfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from pandas.io.common import extension_to_compression

from decoy.cli.io import write_table
from decoy.cli.io._compression import COMPRESSION, csv_compression

_FRAME = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
_CSV = b"id,name\n1,a\n2,b\n"


def test_the_local_suffix_table_equals_pandas_and_has_no_tgz() -> None:
    assert dict(COMPRESSION) == {
        suffix: method for suffix, method in extension_to_compression.items()
    }
    assert ".tgz" not in dict(COMPRESSION)
    suffixes = [suffix for suffix, _m in COMPRESSION]
    for i, earlier in enumerate(suffixes):  # longest first: `.tar.gz` is tried before `.gz`
        assert not any(later != earlier and later.endswith(earlier) for later in suffixes[i + 1 :])


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("out.csv", None),
        ("out.csv.gz", "gzip"),
        ("OUT.CSV.GZ", "gzip"),
        ("out.csv.bz2", "bz2"),
        ("out.csv.xz", "xz"),
        ("out.csv.zst", "zstd"),
        ("out.csv.zip", {"method": "zip", "archive_name": "out.csv"}),
        ("out.csv.tar", {"method": "tar", "archive_name": "out.csv", "mode": "w"}),
        ("out.csv.tar.gz", {"method": "tar", "archive_name": "out.csv", "mode": "w:gz"}),
        ("out.csv.tar.bz2", {"method": "tar", "archive_name": "out.csv", "mode": "w:bz2"}),
        ("out.csv.tar.xz", {"method": "tar", "archive_name": "out.csv", "mode": "w:xz"}),
        ("out.csv.tgz", None),
    ],
)
def test_csv_compression_follows_the_real_name(name: str, expected: object) -> None:
    assert csv_compression(Path("/x") / name) == expected


def _decoded(path: Path) -> bytes:
    raw = path.read_bytes()
    name = path.name
    if name.endswith(".gz") and not name.endswith(".tar.gz"):
        assert raw[:2] == b"\x1f\x8b"
        return gzip.decompress(raw)
    if name.endswith(".bz2") and ".tar" not in name:
        return bz2.decompress(raw)
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.namelist() == ["out.csv"]
            return archive.read("out.csv")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        assert archive.getnames() == ["out.csv"]
        member = archive.extractfile("out.csv")
        assert member is not None
        return member.read()


@pytest.mark.parametrize("suffix", [".gz", ".bz2", ".zip", ".tar.gz"])
@pytest.mark.parametrize("as_arrow", [False, True])
def test_whole_table_write_honours_the_compression_the_name_implies(
    tmp_path: Path, suffix: str, as_arrow: bool
) -> None:
    import pyarrow as pa

    target = tmp_path / f"out.csv{suffix}"
    data = pa.Table.from_pandas(_FRAME) if as_arrow else _FRAME
    write_table(data, "csv", target, private=False)
    assert _decoded(target) == _CSV
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_a_compressed_tar_is_really_compressed(tmp_path: Path) -> None:
    target = tmp_path / "out.csv.tar.gz"
    write_table(_FRAME, "csv", target, private=False)
    assert target.read_bytes()[:2] == b"\x1f\x8b"


def test_plain_csv_stays_plain(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    write_table(_FRAME, "csv", target, private=False)
    assert target.read_bytes() == _CSV
