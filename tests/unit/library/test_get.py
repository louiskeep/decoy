"""`Library.get`: read a stored record back through the engine reader, by the one id rule.

`get` parses the object, drops `id`, canonicalizes and hashes (`records.decode`), so a CRLF or
re-indented copy still reads and a file holding another record under this name is corrupt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from decoy_engine import records
from decoy_engine.reasons import runtime
from tests.unit.library._helpers import envelope, object_path

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, open_library
from decoy.cli.library._errors import RECORD_NOT_FOUND


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "private-project-name"
    project.mkdir()
    return project / DECOY_DIR


def test_get_returns_the_typed_view_and_the_verified_raw_envelope(root: Path) -> None:
    env = envelope()
    library = open_library(root)
    library.put(env)
    got = library.get(env.id)
    assert isinstance(got, records.DecodedRecord)
    assert got.id == env.id and got.kind == "sample-run"
    assert got.raw == json.loads(records.encode(env))
    assert got.view.sample_size == 1  # non-vacuous: the payload went through the read model


def test_an_object_holding_another_record_is_record_corrupt(root: Path) -> None:
    library = open_library(root)
    a, b = envelope(0), envelope(1)
    library.put(a)
    library.put(b)
    object_path(root, a.id).write_bytes(records.encode(b))
    assert records.decode(object_path(root, a.id).read_bytes()).id == b.id  # a valid record
    with pytest.raises(LibraryError) as caught:
        library.get(a.id)
    assert caught.value.code == runtime.RECORD_CORRUPT


def test_a_crlf_rewritten_object_still_reads(root: Path) -> None:
    """MB1-raw-bytes: hashing the file bytes instead of the parsed record turns this red."""
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    pretty = json.dumps(json.loads(stored.read_bytes()), indent=2).replace("\n", "\r\n")
    stored.write_bytes(pretty.encode("utf-8"))
    assert b"\r\n" in stored.read_bytes() and stored.read_bytes() != records.encode(env)
    got = library.get(env.id)
    assert isinstance(got, records.DecodedRecord) and got.id == env.id


def test_an_unknown_kind_is_an_opaque_record(root: Path) -> None:
    library = open_library(root)
    library.put(envelope())  # sets up the library folders
    raw = json.loads(records.encode(envelope()))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["id"] = records.record_id(raw)
    stored = object_path(root, raw["id"])
    stored.parent.mkdir(exist_ok=True)
    stored.write_bytes(records.canonical_bytes(raw))  # as a `git pull` would bring it
    got = library.get(raw["id"])
    assert isinstance(got, records.OpaqueRecord)
    assert (got.kind, got.id) == ("future-thing", raw["id"])


def test_a_missing_id_is_a_coded_not_found_without_a_path(root: Path) -> None:
    library = open_library(root)
    env = envelope()
    library.put(envelope(1))
    assert not object_path(root, env.id).exists()  # non-vacuous: the library exists, this id not
    for missing in (env.id, "sha256:../../etc", "not-an-id"):
        with pytest.raises(LibraryError) as caught:
            library.get(missing)
        assert caught.value.code == RECORD_NOT_FOUND
        assert "private-project-name" not in str(caught.value)
        assert caught.value.__context__ is None
