"""The pure target-format rule (CLI-FMT Part A): suffix claims, issues, messages, one resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoy.cli.io import _targets
from decoy.cli.io._targets import (
    FORMAT_UNKNOWN,
    STREAMING_UNSUPPORTED,
    SUFFIX_MISMATCH,
    TargetFormatError,
    check_target_formats,
    claimed_format,
    format_for_path,
    target_format_issues,
)


@pytest.mark.parametrize(
    ("name", "claimed"),
    [
        ("out.csv", "csv"),
        ("out.CSV", "csv"),
        ("out.parquet", "parquet"),
        ("out.PQ", "parquet"),
        ("out.csv.gz", "csv"),
        ("out.parquet.tar.gz", "parquet"),
        ("out.csv.parquet", "parquet"),
        ("out.txt", None),
        ("out.dat.gz", None),
        ("out", None),
        (".gz", None),
    ],
)
def test_claimed_format(name: str, claimed: str | None) -> None:
    assert claimed_format(Path(name)) == claimed
    assert format_for_path(Path(name)) == (claimed or "csv")


def _config(fmt: str, path: str, **extra: object) -> dict:
    return {"targets": {"t": {"type": "file", "format": fmt, "path": path, **extra}}}


@pytest.mark.parametrize("suffix", [".gz", ".bz2", ".xz", ".zst"])
def test_stream_compressors_stay_allowed_when_chunked(suffix: str) -> None:
    assert target_format_issues(_config("csv", f"/d/out.csv{suffix}"), chunked=True) == []


@pytest.mark.parametrize("suffix", [".zip", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"])
def test_archives_are_refused_when_chunked_only(suffix: str) -> None:
    config = _config("csv", f"/d/out.csv{suffix}")
    assert target_format_issues(config, chunked=False) == []
    (issue,) = target_format_issues(config, chunked=True)
    assert issue.code == STREAMING_UNSUPPORTED


def test_messages_are_value_free() -> None:
    cases = {
        SUFFIX_MISMATCH: _config("parquet", "/zz_marker_dir/out.csv"),
        STREAMING_UNSUPPORTED: _config("fixed_width", "/zz_marker_dir/out.txt", layout={}),
        FORMAT_UNKNOWN: _config("xlsx", "/zz_marker_dir/out.xlsx"),
    }
    for code, config in cases.items():
        (issue,) = target_format_issues(config, chunked=True)
        assert issue.code == code
        with pytest.raises(TargetFormatError) as err:
            check_target_formats(config, chunked=True)
        assert str(err.value) == issue.message
        assert err.value.code == code
        assert err.value.__cause__ is None and err.value.__context__ is None
        for text in (str(err.value), issue.message):
            assert "zz_marker_dir" not in text
            assert "xlsx" not in text
            assert "targets.t" in text
    assert "'parquet'" in target_format_issues(cases[SUFFIX_MISMATCH], chunked=False)[0].message


def test_issues_come_in_sorted_table_order_and_skip_non_file_targets() -> None:
    config = {
        "targets": {
            "b": {"type": "file", "format": "csv", "path": "b.parquet"},
            "a": {"type": "file", "format": "parquet", "path": "a.csv"},
            "c": {"type": "s3", "format": "csv", "path": "c.parquet"},
            "d": "not a dict",
        }
    }
    assert [i.table for i in target_format_issues(config, chunked=False)] == ["a", "b"]


def test_one_path_resolver() -> None:
    from decoy.cli import _sources, demo, run

    assert run._resolve_path is _sources.resolve_path
    assert not hasattr(demo, "_resolve_path")
    assert _targets.resolve_path is _sources.resolve_path
    assert _sources.resolve_path("/abs/x.csv", Path("/base")) == Path("/abs/x.csv")
    assert _sources.resolve_path("rel/x.csv", Path("/base")) == Path("/base/rel/x.csv")


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        ("42", True),
        ("-7", True),
        ("0", True),
        ("42\n", False),
        ("007", False),
        ("-0", False),
        ("9223372036854775807", True),
        ("-9223372036854775808", True),
        ("9223372036854775808", False),
        ("-9223372036854775809", False),
    ],
)
def test_canonical_int_strings(value: str, canonical: bool) -> None:
    import pandas as pd

    got = _targets._coerce_canonical_int_strings(pd.Series([value], dtype=object))
    assert (got is not None) == canonical
