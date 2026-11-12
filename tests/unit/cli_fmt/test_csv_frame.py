"""GEN-FIT-SHAPE C1: both CSV writers print Arrow integers with nulls as integers.

`pyarrow.Table.to_pandas()` widens an integer column that holds a null to float64, so the cell
text becomes `23.0`. `_csv_frame` is the one Arrow-to-pandas step before either CSV writer and
keeps each integer type, signed or unsigned, as its matching pandas nullable dtype.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pyarrow as pa
import pytest

from decoy.cli.io._layout import RunLayout
from decoy.cli.io._targets import _csv_frame, write_chunked_output, write_table

_BIG = 2**64 - 1


def _table() -> pa.Table:
    return pa.table(
        {
            "i8": pa.array([1, None, -3], pa.int8()),
            "i64": pa.array([23, None, -7], pa.int64()),
            "u8": pa.array([1, None, 255], pa.uint8()),
            "u64": pa.array([_BIG, None, 2**63 + 1], pa.uint64()),
            "flag": pa.array([True, None, False], pa.bool_()),
            "price": pa.array([1.5, None, 2.0], pa.float64()),
            "name": pa.array(["a", None, "c"], pa.string()),
        }
    )


def _cells(path: Path, column: str) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [row[column] for row in csv.DictReader(fh)]


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("i8", "Int8"),
        ("i64", "Int64"),
        ("u8", "UInt8"),
        ("u64", "UInt64"),
    ],
)
def test_csv_frame_keeps_each_integer_type(column: str, expected: str) -> None:
    assert str(_csv_frame(_table())[column].dtype) == expected


def test_csv_frame_leaves_non_integer_types_alone() -> None:
    plain = _table().to_pandas()
    frame = _csv_frame(_table())
    for column in ("flag", "price", "name"):
        assert frame[column].dtype == plain[column].dtype


def test_whole_table_write_prints_nullable_integers_without_a_decimal(tmp_path: Path) -> None:
    out = tmp_path / "t.csv"
    write_table(_table(), "csv", out)
    assert _cells(out, "i64") == ["23", "", "-7"]
    assert _cells(out, "i8") == ["1", "", "-3"]
    assert _cells(out, "u8") == ["1", "", "255"]
    assert _cells(out, "price") == ["1.5", "", "2.0"]


def test_whole_table_write_keeps_uint64_above_int64_exact(tmp_path: Path) -> None:
    out = tmp_path / "t.csv"
    write_table(_table(), "csv", out)
    assert _cells(out, "u64") == [str(_BIG), "", str(2**63 + 1)]


def test_chunked_write_prints_nullable_integers_without_a_decimal(tmp_path: Path) -> None:
    out = tmp_path / "t.csv"
    table = _table()
    write_chunked_output(
        iter([table.slice(0, 2), table.slice(2)]),
        "csv",
        str(out),
        RunLayout.fixed(tmp_path),
        empty_schema=None,
    )
    assert _cells(out, "i64") == ["23", "", "-7"]
    assert _cells(out, "u64") == [str(_BIG), "", str(2**63 + 1)]
