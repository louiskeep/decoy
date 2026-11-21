"""G-ONE-TARGET-WRITE: a table is written to a target through `cli/io/_targets.py` only.

Walks every module under `src/decoy/` for table write calls and fails on one outside
`cli/io/_targets.py` unless its (file, enclosing function) is in ALLOWLIST with the exact site
count. Inside the choke point, writes may sit only in the functions named in WRITERS. The
baseline may shrink and never grow (tests/sentry/baselines/target-writes-allow.json, checked by
scripts/dev/ratchet_check.py). The scanner is shared with G-ONE-CSV-READ (`_calls.py`).

Watched:
- any receiver: `.to_csv(`, `.to_parquet(`
- `pyarrow.parquet` (and submodules): `write_table`, `ParquetWriter`, `write_to_dataset`
- `pyarrow.dataset`: `write_dataset`
- `pyarrow.csv`: `write_csv`, `CSVWriter`
- `decoy_engine` (any submodule): `write_fixed_width`

Named limits of a syntax walk: a reference through a runtime-bound name (`getattr(pd, "to_csv")`),
an alias by assignment (`w = pq.write_table; w(t, p)`), `from x import *`, and `exec`. Writer
families not watched (the CLI uses none today): polars `.write_csv` and `.write_parquet`,
`pyarrow.feather`, pandas `to_feather`, `to_excel` and `to_json`. A slice that adds one also
adds it to the watch set. `csv.writer` and `write_text` are not table writers here.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.sentry._ratchet import load_allowlist
from tests.sentry.io_policy._calls import (
    call_contexts,
    call_sites,
    is_staged_name,
    path_arg,
    tally,
)

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "cli/io/_targets.py"
WRITERS = ("_write_table", "write_chunked_output", "_write_fixed_width")
# These two stage their output: every path they write is the temp that `staged_local_target`
# yields. `_write_fixed_width` is exempt: the engine's `write_fixed_width` stages and publishes
# atomically by itself, so wrapping it would stage twice.
STAGED_WRITERS = ("_write_table", "write_chunked_output")
# `_write_table` receives its stager as `stage`; the callers below are checked to pass real ones.
STAGE_CALLS = frozenset({"stage", "staged_local_target", "staged_private_target"})
STAGERS = frozenset({"staged_local_target", "staged_private_target"})

_METHODS = frozenset({"to_csv", "to_parquet"})
_PARQUET = {"write_table", "ParquetWriter", "write_to_dataset"}
_ARROW_CSV = {"write_csv", "CSVWriter"}
_ARROW_DATASET = {"write_dataset"}


@dataclass(frozen=True)
class AllowedWrite:
    file: str  # relative to src/decoy
    function: str
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedWrite, ...] = tuple(
    AllowedWrite(*key.split("::"), e["sites"], e["reason"])
    for key, e in load_allowlist("target-writes-allow").items()
)


def _under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _owns(module: str, name: str) -> bool:
    if _under(module, "pyarrow.parquet"):
        return name in _PARQUET
    if _under(module, "pyarrow.csv"):
        return name in _ARROW_CSV
    if _under(module, "pyarrow.dataset"):
        return name in _ARROW_DATASET
    return _under(module, "decoy_engine") and name == "write_fixed_width"


def write_sites(source: str) -> list[tuple[int, str]]:
    """Return (line, enclosing function or '<module>') for each watched write call."""
    return call_sites(source, qualified_match=_owns, method_names=_METHODS)


def _tally(root: Path) -> dict[tuple[str, str], int]:
    return tally(root, skip=CHOKE_POINT, finder=write_sites)


def _allowed() -> dict[tuple[str, str], int]:
    return {(a.file, a.function): a.sites for a in ALLOWLIST}


def test_no_table_write_outside_the_writer_module() -> None:
    found, allowed = _tally(SRC), _allowed()
    extra = {k: n for k, n in found.items() if allowed.get(k, 0) < n}
    assert not extra, f"table write outside cli/io/_targets.py: {sorted(extra)}"


def test_allowlist_entries_are_live_and_exact() -> None:
    found = _tally(SRC)
    stale = {k: n for k, n in _allowed().items() if found.get(k, 0) != n}
    assert not stale, f"allowlist entries that no longer match the code: {sorted(stale)}"


def test_allowlist_has_reasons_and_unique_identities() -> None:
    assert len(_allowed()) == len(ALLOWLIST)
    assert all(len(a.reason) >= 15 for a in ALLOWLIST)


def _outside_writers(source: str) -> list[str]:
    return sorted({scope for _l, scope in write_sites(source) if scope not in WRITERS})


def test_writer_module_writes_only_in_its_writers() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    scopes = {scope for _l, scope in write_sites(source)}
    assert _outside_writers(source) == []
    assert set(WRITERS) <= scopes, f"writers with no write site: {sorted(set(WRITERS) - scopes)}"
    seeded = source + "\n\ndef sneaky(df, p):\n    df.to_csv(p)\n"
    assert _outside_writers(seeded) == ["sneaky"]


@pytest.mark.parametrize(
    "source",
    [
        "import pyarrow.parquet as pq\ndef f(t, p):\n    pq.write_table(t, p)\n",
        "import pyarrow.parquet\ndef f(t, p):\n    pyarrow.parquet.write_table(t, p)\n",
        "from pyarrow import parquet\ndef f(t, p):\n    parquet.write_table(t, p)\n",
        "from pyarrow.parquet import write_table as wt\ndef f(t, p):\n    wt(t, p)\n",
        "import pyarrow.parquet as pq\ndef f(p, s):\n    pq.ParquetWriter(p, s)\n",
        "import pyarrow.parquet as pq\ndef f(t, p):\n    pq.write_to_dataset(t, p)\n",
        "import pyarrow.csv\ndef f(t, p):\n    pyarrow.csv.write_csv(t, p)\n",
        "import pyarrow.csv as pc\ndef f(p, s):\n    pc.CSVWriter(p, s)\n",
        "import pyarrow.parquet.core\ndef f(t, p):\n    pyarrow.parquet.core.write_table(t, p)\n",
        "import pyarrow.dataset as ds\ndef f(t, p):\n    ds.write_dataset(t, p)\n",
        "import pyarrow as pa\ndef f(t, p):\n    pa.parquet.write_table(t, p)\n",
        "import pyarrow.parquet as pq\ndef f(pool, t, p):\n    pool.submit(pq.write_table, t, p)\n",
        "import functools\nimport pyarrow.parquet as pq\ndef f(t, p):\n    return functools.partial(pq.write_table, t, p)\n",
        "from pyarrow.parquet import write_table\ndef f(pool, t, p):\n    pool.submit(write_table, t, p)\n",
        "def f(pool, frame, p):\n    pool.submit(frame.to_csv, p)\n",
        "def f(frame, p):\n    frame.to_parquet(p)\n",
        "def f(frame, p):\n    frame.to_csv(p)\n",
        "def f(t, p):\n    t.to_pandas().to_csv(p)\n",
        "import pandas as pd\ndef f(frame, p):\n    pd.DataFrame.to_csv(frame, p)\n",
        "import decoy_engine as de\ndef f(fr, lay, p):\n    de.write_fixed_width(fr, lay, p)\n",
        "from decoy_engine import write_fixed_width\ndef f(fr, lay, p):\n    write_fixed_width(fr, lay, p)\n",
    ],
)
def test_walk_sees_each_spelling(source: str) -> None:
    assert [scope for _l, scope in write_sites(source)] == ["f"]


@pytest.mark.parametrize(
    "source",
    [
        "def f(t, writer):\n    writer.write_table(t)\n",
        "def f(t, p, make):\n    w = make(p)\n    w.write_table(t)\n",
        "class C:\n    def f(self, t):\n        self.sink.write_table(t)\n",
        "def to_csvish(x):\n    return x\ndef f(x):\n    return to_csvish(x)\n",
        "import pyarrow.parquet as pq\ndef f(p):\n    return pq.read_table(p)\n",
    ],
)
def test_walk_ignores_lookalikes(source: str) -> None:
    assert write_sites(source) == []


def test_scopes_are_qualified_names() -> None:
    src = (
        "class C:\n    def m(self, df, p):\n        df.to_csv(p)\n"
        "def outer(df, p):\n    def inner():\n        df.to_csv(p)\n    inner()\n"
    )
    assert [scope for _l, scope in write_sites(src)] == ["C.m", "outer.inner"]


def test_nested_function_named_like_a_writer_does_not_count_as_the_writer() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    seeded = source + "\n\ndef other(df, p):\n    def write_table():\n        df.to_csv(p)\n"
    assert _outside_writers(seeded) == ["other.write_table"]


def test_imports_are_scoped_to_where_they_are_made() -> None:
    inner_only = (
        "def g():\n    import pyarrow.parquet as pq\n    return pq\n"
        "def f(t, p):\n    pq.write_table(t, p)\n"
    )
    assert write_sites(inner_only) == []
    visible = "import pyarrow.parquet as pq\ndef f(t, p):\n    pq.write_table(t, p)\n"
    assert [scope for _l, scope in write_sites(visible)] == ["f"]
    own = "def f(t, p):\n    import pyarrow.parquet as pq\n    pq.write_table(t, p)\n"
    assert [scope for _l, scope in write_sites(own)] == ["f"]


def test_seeded_bypass_is_red(tmp_path: Path) -> None:
    pkg = tmp_path / "cli"
    pkg.mkdir()
    seeds = {
        "sneaky.py": "def save(df, p):\n    df.to_csv(p)\n",
        "sneaky2.py": "import pyarrow.parquet as pq\ndef save(t, p):\n    pq.write_table(t, p)\n",
        "sneaky3.py": (
            "from decoy_engine import write_fixed_width\n"
            "def save(f, lay, p):\n    write_fixed_width(f, lay, p)\n"
        ),
    }
    for name, text in seeds.items():
        (pkg / name).write_text(text, encoding="utf-8")
    assert _tally(tmp_path) == {(f"cli/{name}", "save"): 1 for name in seeds}


def unstaged_writes(source: str) -> list[tuple[int, str]]:
    """(line, scope) for each write in a staged writer whose path is not its staged temp."""
    bad = []
    for call, scope, names in call_contexts(
        source, qualified_match=_owns, method_names=_METHODS, with_calls=STAGE_CALLS
    ):
        if scope not in STAGED_WRITERS:
            continue
        func = call.func
        member = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if member == "write_fixed_width":
            continue
        if not is_staged_name(path_arg(call, member), names):
            bad.append((call.lineno, scope))
    return bad


def test_staged_writers_write_only_to_their_staged_temp() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    assert unstaged_writes(source) == []
    covered = {
        scope
        for _c, scope, _n in call_contexts(
            source, qualified_match=_owns, method_names=_METHODS, with_calls=STAGE_CALLS
        )
    }
    assert set(STAGED_WRITERS) <= covered, "a staged writer has no write call to check"


# OUTPUT-METADATA-LEAK (CC-6): a Parquet target carries only the engine's allow-listed metadata.
# Each Parquet sink in these writers takes a value the same function made with `output_table`
# or `output_schema`, so source metadata cannot reach a published file.
SANITIZED_WRITERS = ("_write_table", "write_chunked_output")
_SANITIZERS = frozenset({"output_table", "output_schema"})
# (positional index, keyword) of the value each Parquet sink call writes.
_PARQUET_VALUE: dict[str, tuple[int, str] | None] = {
    "write_table": (0, "table"),
    "write_to_dataset": (0, "table"),
    "ParquetWriter": (1, "schema"),
    "to_parquet": None,  # the receiver is the data; never sanitized, always a finding
}


def _makes(expr: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) in _SANITIZERS
        for n in ast.walk(expr)
    )


def _sanitized_before(func: ast.AST, name: str, line: int) -> bool:
    """The last assignment to `name` above `line` in `func` is made by a sanitizer call."""
    last: tuple[int, bool] | None = None
    for node in ast.walk(func):
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None or node.lineno >= line:
            continue
        if any(t.id == name for t in targets) and (last is None or node.lineno > last[0]):
            last = (node.lineno, _makes(value))
    return last is not None and last[1]


def _is_sanitized(expr: ast.expr | None, func: ast.AST, line: int) -> bool:
    if isinstance(expr, ast.Call):
        return _makes(expr)
    return isinstance(expr, ast.Name) and _sanitized_before(func, expr.id, line)


def unsanitized_parquet_writes(source: str) -> list[tuple[int, str]]:
    """(line, scope) for each Parquet sink in a sanitized writer fed a value it did not sanitize.

    Also covers the per-chunk `writer.write_table(x)` method call: `x` must be sanitized too.
    """
    tree = ast.parse(source)
    funcs = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name in SANITIZED_WRITERS
    }
    bad = []
    for call, scope, _names in call_contexts(
        source, qualified_match=_owns, method_names=_METHODS, with_calls=STAGE_CALLS
    ):
        if scope not in SANITIZED_WRITERS or scope not in funcs:
            continue
        func = call.func
        member = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if member not in _PARQUET_VALUE:
            continue
        slot = _PARQUET_VALUE[member]
        value = None
        if slot is not None:
            value = next((k.value for k in call.keywords if k.arg == slot[1]), None)
            if value is None and len(call.args) > slot[0]:
                value = call.args[slot[0]]
        if slot is None or not _is_sanitized(value, funcs[scope], call.lineno):
            bad.append((call.lineno, scope))
    for scope, node in funcs.items():  # the chunk loop writes through a bound writer
        for n in ast.walk(node):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "write_table"
                and getattr(n.func.value, "id", "") == "writer"
                and not _is_sanitized(n.args[0] if n.args else None, node, n.lineno)
            ):
                bad.append((n.lineno, scope))
    return bad


def test_parquet_sinks_in_the_writers_take_sanitized_values() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    assert unsanitized_parquet_writes(source) == []


_PQ_PRELUDE = "import pyarrow.parquet as pq\nfrom decoy_engine import output_schema, output_table\n"


@pytest.mark.parametrize(
    "scope, body",
    [
        ("_write_table", "    pq.write_table(data, path)\n"),
        ("_write_table", "    data.to_parquet(path)\n"),
        (
            "_write_table",
            "    table = output_table(data)\n    table = data\n    pq.write_table(table, p)\n",
        ),
        ("_write_table", "    pq.write_table(data)\n"),
        ("write_chunked_output", "    pq.ParquetWriter(path, first.schema)\n"),
        ("write_chunked_output", "    s = first.schema\n    pq.ParquetWriter(path, schema=s)\n"),
        (
            "write_chunked_output",
            "    s = output_schema(first.schema)\n    with pq.ParquetWriter(p, s) as writer:\n"
            "        writer.write_table(first)\n",
        ),
    ],
)
def test_the_sanitized_rule_is_red_on_seeds(scope: str, body: str) -> None:
    source = _PQ_PRELUDE + f"def {scope}(data, path, first, p):\n" + body
    assert unsanitized_parquet_writes(source) != []


@pytest.mark.parametrize(
    "scope, body",
    [
        ("_write_table", "    pq.write_table(output_table(data), path)\n"),
        ("_write_table", "    table = output_table(data)\n    pq.write_table(table, path)\n"),
        (
            "write_chunked_output",
            "    s = output_schema(first.schema)\n    pq.ParquetWriter(p, s)\n",
        ),
        (
            "write_chunked_output",
            "    s = output_schema(first.schema)\n    with pq.ParquetWriter(p, s) as writer:\n"
            "        writer.write_table(output_table(first))\n",
        ),
        ("_write_fixed_width", "    pq.write_table(data, path)\n"),
    ],
)
def test_the_sanitized_rule_is_green_on_sanitized_shapes(scope: str, body: str) -> None:
    source = _PQ_PRELUDE + f"def {scope}(data, path, first, p):\n" + body
    assert unsanitized_parquet_writes(source) == []


_STAGED_PRELUDE = (
    "import pyarrow.parquet as pq\nfrom decoy_engine import write_fixed_width\n"
    "from decoy._atomic import staged_local_target, staged_private_target\n"
)


@pytest.mark.parametrize(
    "body",
    [
        "    data.to_csv(path)\n",
        "    with staged_local_target(path) as tmp:\n        data.to_csv(path)\n",
        "    with staged_local_target(path) as tmp:\n        data.to_csv(other)\n",
        "    with staged_local_target(path) as tmp:\n        data.to_parquet(path=path)\n",
        "    data.to_parquet(path=path)\n",
        "    with staged_local_target(path) as tmp:\n        pq.write_table(data, path)\n",
        "    with staged_local_target(path) as tmp:\n"
        "        pq.ParquetWriter(where=str(path), schema=s)\n",
        "    with staged_local_target(path) as tmp:\n        pass\n    data.to_csv(tmp)\n",
        "    with staged_local_target(path) as tmp:\n        pq.write_to_dataset(data, tmp)\n",
    ],
)
def test_staged_path_rule_is_red_on_seeds(body: str) -> None:
    source = _STAGED_PRELUDE + "def _write_table(data, path):\n" + body
    assert unstaged_writes(source) != []


@pytest.mark.parametrize(
    "body",
    [
        "    with staged_local_target(path) as tmp:\n        data.to_csv(tmp)\n",
        "    with staged_local_target(path) as tmp:\n        pq.write_table(data, str(tmp))\n",
        "    with staged_local_target(path) as tmp:\n"
        "        pq.ParquetWriter(where=str(tmp), schema=s)\n",
        "    with staged_local_target(path) as tmp:\n        data.to_parquet(path=tmp)\n",
        "    write_fixed_width(frame, layout, path)\n",
        "    with staged_private_target(path) as a, other() as b:\n"
        "        data.to_csv(path_or_buf=a)\n",
    ],
)
def test_staged_path_rule_is_green_on_staged_and_exempt_shapes(body: str) -> None:
    assert unstaged_writes(_STAGED_PRELUDE + "def _write_table(data, path):\n" + body) == []


def test_staged_path_rule_only_covers_the_two_staged_writers() -> None:
    source = _STAGED_PRELUDE + "def _write_fixed_width(data, path):\n    data.to_csv(path)\n"
    assert unstaged_writes(source) == []


def _stagers_passed_to_write_table(source: str) -> list[str]:
    """Names passed as the last argument of each `_write_table(...)` call in the module."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_write_table":
            last = node.args[-1] if node.args else None
            names.append(last.id if isinstance(last, ast.Name) else "<other>")
    return names


def test_the_public_whole_table_writers_pass_a_real_stager() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    passed = _stagers_passed_to_write_table(source)
    assert sorted(passed) == ["staged_local_target", "staged_private_target"]
    assert set(passed) <= STAGERS
    seeded = source + "\ndef sneaky(d, f, p):\n    _write_table(d, f, p, None, open)\n"
    assert "open" in _stagers_passed_to_write_table(seeded)


# Restored original values must be written owner-only: these two commands may call only the
# private entry point, never `write_table`, `write_targets` or `write_chunked_output`.
PRIVATE_ONLY = ("cli/unmask.py", "cli/tokenize.py")
_PUBLIC_WRITERS = frozenset({"write_table", "write_targets", "write_chunked_output"})


def _owns_public_writer(module: str, name: str) -> bool:
    return _under(module, "decoy.cli.io") and name in _PUBLIC_WRITERS


def public_writer_uses(source: str) -> list[tuple[int, str]]:
    return call_sites(source, qualified_match=_owns_public_writer)


def test_restoring_commands_use_only_the_private_table_writer() -> None:
    for rel in PRIVATE_ONLY:
        source = (SRC / rel).read_text(encoding="utf-8")
        assert public_writer_uses(source) == [], rel
    unmask = (SRC / "cli/unmask.py").read_text(encoding="utf-8")
    assert "write_private_table" in unmask


@pytest.mark.parametrize(
    "source",
    [
        "from decoy.cli.io import write_table\ndef f(t, p):\n    write_table(t, 'csv', p)\n",
        "from decoy.cli.io._targets import write_table as w\ndef f(t, p):\n    w(t, 'csv', p)\n",
        "import decoy.cli.io as io\ndef f(t, p):\n    io.write_table(t, 'csv', p)\n",
        "from decoy.cli.io import write_targets\ndef f(c, o, b):\n    write_targets(c, o, b)\n",
    ],
)
def test_the_private_only_rule_is_red_on_seeds(source: str) -> None:
    assert public_writer_uses(source) != []


def test_the_private_only_rule_is_green_on_the_private_writer() -> None:
    source = (
        "from decoy.cli.io import write_private_table\n"
        "def f(t, p):\n    write_private_table(t, 'csv', p)\n"
    )
    assert public_writer_uses(source) == []
