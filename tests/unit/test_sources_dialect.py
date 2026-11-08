"""Unit tests for the CSV read point in `decoy.cli._sources` (CLI-DIALECT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from decoy_engine import VALIDATION_CODES, PipelineValidationError

from decoy.cli._sources import iter_source_chunks, read_source

_HEADERLESS: dict[str, Any] = {
    "type": "file",
    "format": "csv",
    "path": "secret_name_file.csv",
    "has_header": False,
    "column_names": ["id", "name", "age"],
}

_MISFITS: dict[str, tuple[bytes, str]] = {
    "extra_field": (b"1,Alice,31,zz_marker_a\n", "SOURCE_FILE_COLUMN_COUNT_MISMATCH"),
    "short_row": (b"1,Alice\n", "SOURCE_FILE_COLUMN_COUNT_MISMATCH"),
    "no_rows": (b"\n\n", "SOURCE_FILE_COLUMN_COUNT_MISMATCH"),
    "nul": (b"1,zz_marker_b,3\x001\n", "SOURCE_FILE_NUL_BYTE"),
    "lone_cr": (b"1,Alice,31\r2,zz_marker_b,4\r", "SOURCE_FILE_LONE_CR"),
    "open_quote": (b'1,2,"3\n', "SOURCE_FILE_COLUMN_COUNT_MISMATCH"),
}


def _refused(tmp_path: Path, case: str, fn: str) -> PipelineValidationError:
    content, _ = _MISFITS[case]
    (tmp_path / "secret_name_file.csv").write_bytes(content)
    with pytest.raises(PipelineValidationError) as caught:
        if fn == "whole":
            read_source("events", _HEADERLESS, tmp_path)
        else:
            list(iter_source_chunks("events", _HEADERLESS, tmp_path, 2))
    return caught.value


@pytest.mark.parametrize("fn", ["whole", "chunks"])
@pytest.mark.parametrize("case", sorted(_MISFITS))
def test_cli_read_errors_are_coded_and_value_free(tmp_path: Path, case: str, fn: str) -> None:
    err = _refused(tmp_path, case, fn)
    code = getattr(VALIDATION_CODES, _MISFITS[case][1])
    assert err.code == code
    assert str(err).startswith(f"{code}: source events ")
    for text in (str(err), repr(err)):
        for leaked in ("zz_marker_a", "zz_marker_b", "secret_name_file", str(tmp_path)):
            assert leaked not in text
    assert err.__cause__ is None
    assert err.__context__ is None


def test_iter_source_chunks_fails_at_call(tmp_path: Path) -> None:
    (tmp_path / "secret_name_file.csv").write_bytes(b"1,Alice,31,x\n")
    with pytest.raises(PipelineValidationError):
        iter_source_chunks("events", _HEADERLESS, tmp_path, 2)


def test_read_report_source_declared_and_default(tmp_path: Path) -> None:
    from decoy.cli._sources import read_report_source

    declared = tmp_path / "pipe.txt"
    declared.write_text("1|Alice\n2|Bob\n", encoding="utf-8")
    cfg = {
        "sources": {
            "t": {
                "format": "csv",
                "path": "pipe.txt",
                "delimiter": "|",
                "has_header": False,
                "column_names": ["id", "name"],
            }
        }
    }
    got = read_report_source(declared, cfg, tmp_path)
    assert list(got.columns) == ["id", "name"]
    assert got["id"].tolist() == [1, 2]
    other = tmp_path / "other.csv"
    other.write_text("a,b\n1,2\n", encoding="utf-8")
    pd.testing.assert_frame_equal(read_report_source(other, cfg, tmp_path), pd.read_csv(other))
