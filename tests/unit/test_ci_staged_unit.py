"""Pure-function checks for the staged scan's glob scope and name-status parsing."""

from __future__ import annotations

import pytest

from decoy.ci.staged import glob_matches, parse_name_status_z


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("fixtures/**", "fixtures/a.txt", True),
        ("fixtures/**", "fixtures/a/b/c.txt", True),
        ("fixtures/**", "fixtures", False),
        ("fixtures/**", "other/fixtures/a.txt", False),
        ("**", "anything/at/all", True),
        ("**/deep.cfg", "deep.cfg", True),
        ("**/deep.cfg", "a/b/deep.cfg", True),
        ("**/deep.cfg", "a/b/notdeep.cfg", False),
        ("a/**/b.txt", "a/b.txt", True),
        ("a/**/b.txt", "a/x/y/b.txt", True),
        ("a/**/b.txt", "ax/b.txt", False),
        ("*.txt", "top.txt", True),
        ("*.txt", "dir/top.txt", False),
        ("dir/f?.md", "dir/f1.md", True),
        ("dir/f?.md", "dir/f12.md", False),
        ("dir/f?.md", "dir/f/.md", False),
        ("d.ir/*", "dXir/a", False),  # the dot is literal
        ("a+b/*", "a+b/c", True),  # regex metacharacters are literal
        ("dir/*", "dir/new\nline", True),  # newlines in names do not break matching
    ],
)
def test_glob_scope_semantics(glob: str, path: str, expected: bool) -> None:
    assert glob_matches(glob, path) is expected


def test_name_status_parser_reads_exactly_the_fields_each_status_carries() -> None:
    raw = b"A\0a\0M\0b\0D\0c\0T\0d\0U\0e\0R087\0old\0new\0C100\0src\0dup\0"
    assert parse_name_status_z(raw) == [
        ("A", b"a"),
        ("M", b"b"),
        ("D", b"c"),
        ("T", b"d"),
        ("U", b"e"),
        ("R", b"new"),
        ("C", b"dup"),
    ]
    assert parse_name_status_z(b"") == []


@pytest.mark.parametrize("raw", [b"A\0", b"R100\0only\0", b"\0a\0", b"9\0a\0", b"a\0b\0"])
def test_name_status_parser_rejects_malformed_streams(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_name_status_z(raw)
