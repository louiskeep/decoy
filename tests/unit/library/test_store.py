"""The store's acceptance rows: B1-atomic-kill, B1-idempotent, B1-no-clobber, B1-existing-corrupt,
B1-link-exists, B1-concurrent, plus `get`, `resolve` and the `LAYOUT` file.

Races and kills run in child processes, as two CLI invocations would.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from decoy.cli.library import LibraryError, open_library
from decoy.cli.library._errors import LIBRARY_LAYOUT_NEWER, RECORD_LINK_MISSING
from decoy_engine import records
from decoy_engine.reasons import runtime
from tests.unit.library._helpers import (
    envelope,
    object_files,
    object_path,
    run_child,
    start_child,
)

from decoy.cli.io import DECOY_DIR


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


# -- put, get, resolve ------------------------------------------------------------------------


def test_put_stores_the_canonical_bytes_under_the_id(root: Path) -> None:
    env = envelope()
    result = open_library(root).put(env)
    assert (result.id, result.created) == (env.id, True)
    stored = object_path(root, env.id)
    assert stored.read_bytes() == records.encode(env)
    assert json.loads((root / "library" / "LAYOUT").read_text(encoding="utf-8")) == {"layout": 1}


def test_get_returns_the_verified_record_and_none_when_absent(root: Path) -> None:
    env = envelope()
    library = open_library(root)
    assert library.get(env.id) is None
    library.put(env)
    got = library.get(env.id)
    assert isinstance(got, records.DecodedRecord) and got.id == env.id


def test_get_refuses_a_file_whose_content_is_another_record(root: Path) -> None:
    library = open_library(root)
    a, b = envelope(0), envelope(1)
    library.put(a)
    library.put(b)
    object_path(root, a.id).write_bytes(records.encode(b))
    with pytest.raises(LibraryError) as caught:
        library.get(a.id)
    assert caught.value.code == runtime.RECORD_CORRUPT


def test_resolve_finds_ids_by_a_prefix_of_eight_or_more_hex(root: Path) -> None:
    library = open_library(root)
    envs = [envelope(n) for n in range(3)]
    for env in envs:
        library.put(env)
    target = envs[1].id
    digest = target.removeprefix("sha256:")
    assert library.resolve(digest[:8]) == (target,)
    assert library.resolve(target) == (target,)
    assert library.resolve(f"sha256:{digest[:12]}") == (target,)
    assert library.resolve(digest[:7]) == ()  # too short to be a prefix
    assert library.resolve("zz" * 5) == ()
    assert library.resolve("0" * 64) == ()


def test_a_newer_layout_refuses_writes(root: Path) -> None:
    library = open_library(root)
    library.put(envelope(0))
    (root / "library" / "LAYOUT").write_text('{"layout":2}', encoding="utf-8")
    with pytest.raises(LibraryError) as caught:
        open_library(root).put(envelope(1))
    assert caught.value.code == LIBRARY_LAYOUT_NEWER
    assert len(object_files(root)) == 1


# -- B1-idempotent ----------------------------------------------------------------------------


_HOLD_OPEN = (
    "import sys, time\n"
    "handle = open(sys.argv[1], 'rb')\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n"
)


def test_putting_the_same_envelope_twice_is_one_file_and_no_error(root: Path) -> None:
    """MB1-replace: always using `os.replace` gives a new inode and `created` True; red."""
    env = envelope()
    library = open_library(root)
    assert library.put(env).created is True
    stored = object_path(root, env.id)
    inode = os.stat(stored).st_ino
    holder = start_child(_HOLD_OPEN, str(stored))
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        again = library.put(env)
    finally:
        holder.kill()
        holder.wait()
    assert (again.id, again.created) == (env.id, False)
    assert os.stat(stored).st_ino == inode
    assert object_files(root) == [stored]


# -- B1-existing-corrupt ----------------------------------------------------------------------


def test_an_existing_object_with_another_payload_is_record_corrupt(root: Path) -> None:
    """MB1-trust-existing: treating any existing file as success turns this red."""
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    tampered = records.encode(env).replace(b'"sample_size":1', b'"sample_size":9')
    assert tampered != records.encode(env)  # non-vacuous: the payload really changed
    stored.write_bytes(tampered)
    with pytest.raises(LibraryError) as caught:
        library.put(env)
    assert caught.value.code == runtime.RECORD_CORRUPT
    assert stored.read_bytes() == tampered  # reported, never repaired in place


def test_a_reformatted_existing_object_is_not_corrupt(root: Path) -> None:
    """The id rule parses before hashing, so a CRLF or re-indented copy is the same record."""
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    pretty = json.dumps(json.loads(stored.read_bytes()), indent=2).replace("\n", "\r\n")
    stored.write_bytes(pretty.encode("utf-8"))
    assert library.put(env).created is False


# -- B1-link-exists ---------------------------------------------------------------------------


def test_a_link_to_a_missing_record_is_refused_and_writes_nothing(root: Path) -> None:
    """MB1-no-link-check: skipping the target check stores the record; red."""
    target = envelope(0)
    linked = envelope(1, links=[target.id])
    assert [link.id for link in linked.links] == [target.id]  # non-vacuous: one link
    with pytest.raises(LibraryError) as caught:
        open_library(root).put(linked)
    assert caught.value.code == RECORD_LINK_MISSING
    assert not root.exists()
    library = open_library(root)
    library.put(target)
    with pytest.raises(LibraryError):
        library.put(envelope(2, links=[envelope(3).id]))
    assert library.put(linked).created is True
    assert len(object_files(root)) == 2


# -- B1-atomic-kill ---------------------------------------------------------------------------

_KILLED_MID_WRITE = (
    "import pathlib, sys, time\n"
    "from tests.unit.library._helpers import envelope\n"
    "from decoy.cli.library import open_library\n"
    "real = pathlib.Path.write_bytes\n"
    "def half(self, data):\n"
    "    if b'sample-run' not in data:\n"
    "        return real(self, data)\n"
    "    with open(self, 'wb') as fh:\n"
    "        fh.write(data[: len(data) // 2])\n"
    "        fh.flush()\n"
    "    print('writing', len(data), flush=True)\n"
    "    time.sleep(60)\n"
    "pathlib.Path.write_bytes = half\n"
    "open_library(pathlib.Path(sys.argv[1])).put(envelope())\n"
)


def test_a_writer_killed_mid_put_leaves_no_readable_record(root: Path) -> None:
    """MB1-direct: writing to the final name leaves a half record there; red."""
    child = start_child(_KILLED_MID_WRITE, str(root))
    try:
        assert child.stdout is not None
        line = child.stdout.readline().split()
    finally:
        child.kill()  # SIGKILL on POSIX, TerminateProcess on Windows
        child.wait()
    assert line and line[0] == "writing", child.stderr.read() if child.stderr else ""
    full = int(line[1])
    assert object_files(root) == []
    temps = [p for p in (root / "library" / "tmp").iterdir() if p.is_file()]
    assert len(temps) == 1 and 0 < temps[0].stat().st_size < full  # killed mid-write
    again = open_library(root).put(envelope())
    assert again.created is True and open_library(root).get(again.id) is not None


# -- B1-no-clobber ----------------------------------------------------------------------------

_RACE_SAME = (
    "import os, sys, time\n"
    "from pathlib import Path\n"
    "from tests.unit.library._helpers import envelope\n"
    "from decoy.cli.library import open_library\n"
    "base, go = Path(sys.argv[1]), Path(sys.argv[2])\n"
    "seen = {'replace': 0, 'link': 0}\n"
    "real_replace, real_link = os.replace, os.link\n"
    "def replace(src, dst, **kw):\n"
    "    if 'objects' in str(dst):\n"
    "        seen['replace'] += 1\n"
    "    return real_replace(src, dst, **kw)\n"
    "def link(src, dst, **kw):\n"
    "    if 'objects' in str(dst):\n"
    "        seen['link'] += 1\n"
    "    return real_link(src, dst, **kw)\n"
    "os.replace, os.link = replace, link\n"
    "env = envelope()\n"
    "while not go.exists():\n"
    "    time.sleep(0.001)\n"
    "created = [open_library(base / str(i)).put(env).created for i in range(50)]\n"
    "print(''.join('1' if c else '0' for c in created), seen['replace'], seen['link'])\n"
)


def test_two_processes_racing_one_envelope_never_clobber(tmp_path: Path) -> None:
    """MB1-check-then-replace: `exists()` then `os.replace` shows replace calls; red."""
    go = tmp_path / "go"
    kids = [start_child(_RACE_SAME, str(tmp_path / "libs"), str(go)) for _ in range(2)]
    go.touch()
    outs = []
    for kid in kids:
        out, err = kid.communicate(timeout=180)
        assert kid.returncode == 0, err
        outs.append(out.split())
    for _flags, replaces, links in outs:
        assert replaces == "0"
        assert int(links) >= 1  # non-vacuous: the spy saw the record moves
    env = envelope()
    for i in range(50):
        lib_root = tmp_path / "libs" / str(i)
        assert object_files(lib_root) == [object_path(lib_root, env.id)]
        assert open_library(lib_root).get(env.id) is not None
        assert int(outs[0][0][i]) + int(outs[1][0][i]) == 1  # exactly one creator per round


# -- B1-concurrent ----------------------------------------------------------------------------

_PUT_MANY = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from tests.unit.library._helpers import envelope\n"
    "from decoy.cli.library import open_library\n"
    "root, start, go = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])\n"
    "while not go.exists():\n"
    "    time.sleep(0.001)\n"
    "library = open_library(root)\n"
    "print(sum(library.put(envelope(n)).created for n in range(start, start + 50)))\n"
)


def test_two_processes_put_fifty_records_each(root: Path, tmp_path: Path) -> None:
    """MB1-shared-tmp: a fixed temp name lets one writer's bytes land under another id; red."""
    go = tmp_path / "go"
    kids = [start_child(_PUT_MANY, str(root), str(start), str(go)) for start in (0, 50)]
    go.touch()
    for kid in kids:
        out, err = kid.communicate(timeout=180)
        assert kid.returncode == 0, err
        assert out.strip() == "50"
    files = object_files(root)
    assert len(files) == 100
    library = open_library(root)
    ids = {envelope(n).id for n in range(100)}
    for path in files:
        decoded = records.decode(path.read_bytes())
        assert decoded.id in ids
        assert path == Path(object_path(root, decoded.id))
        assert library.get(decoded.id) is not None
    assert [p for p in (root / "library" / "tmp").iterdir()] == []


def test_run_child_helper_reaches_the_library(root: Path) -> None:
    out = run_child(
        "import sys\nfrom pathlib import Path\n"
        "from tests.unit.library._helpers import envelope\n"
        "from decoy.cli.library import open_library\n"
        "print(open_library(Path(sys.argv[1])).put(envelope()).created)\n",
        str(root),
    )
    assert out.strip() == "True" and len(object_files(root)) == 1
