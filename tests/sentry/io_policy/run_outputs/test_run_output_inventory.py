"""G-ONE-OUTPUT-INVENTORY: `run_outputs` lists every file `decoy run` writes.

The collision rule reads only `run_outputs` (`cli/io/_run_outputs.py`), so a writer that is not
listed there is not protected from the record library root or from another output. Four parts
keep the list complete (plan L3a Revision 8, Rule 1):

(i) The run-reached modules are computed, never listed: the static import closure of
    `decoy.cli.run` inside `src/decoy/`, minus `cli/library/` (library-owned, guarded by
    G-LIB-FS) and the implementation files `_atomic.py` and `_private_file.py`. The walk follows
    imports in function bodies, because run code imports lazily.
(ii) In those modules every call to a write primitive has a `file_sinks.toml` row with an
    `output_kind`: an `OutputKind` value, or `not-run`. The scan is G-ONE-PRIVATE-FILE's
    `collect()` with the added primitives passed in as a parameter. Entry-point calls get rows
    with `disposition = "entry"`.
(iii) `resolved_output_collisions` reads no second source of outputs, and the default report name
    has one derivation.
(iv) A write audit: real runs in a temp project, and every file, link or folder created or
    changed outside the library root is a `run_outputs` path or a folder above one.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF
from tests.sentry.io_policy.test_private_files import (
    ENTRY,
    IMPLEMENTATION,
    OUTPUT_PRIMITIVES,
    PRIVATE_ENTRY,
    ROWS,
    SRC,
    Row,
    collect,
    is_entry_row,
    live_files,
)
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.io import OutputPlacement, run_outputs
from decoy.cli.io._run_outputs import OutputKind

ROOT_MODULE = "decoy.cli.run"
LIBRARY_PREFIX = "cli/library/"
NOT_RUN = "not-run"
KINDS = frozenset(kind.value for kind in OutputKind) | {NOT_RUN}


# --- (i) the run-reached modules ----------------------------------------------------------


def _module_names(files: Mapping[str, str]) -> dict[str, str]:
    """Dotted module name to the relative path of its file."""
    names: dict[str, str] = {}
    for rel in files:
        parts = list(Path(rel).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        names[".".join(["decoy", *parts]) if parts else "decoy"] = rel
    return names


def _imported(tree: ast.AST, known: Mapping[str, str]) -> set[str]:
    """Every first-party module an import statement names, at any depth in the file."""
    named: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            named.add(node.module)
            named.update(f"{node.module}.{alias.name}" for alias in node.names)
    return {name for name in named if name in known}


def run_reached(files: Mapping[str, str], root: str = ROOT_MODULE) -> set[str]:
    """The relative paths of the modules `decoy run` can reach (part i)."""
    known = _module_names(files)
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        rel = known[name]
        if name in seen or rel.startswith(LIBRARY_PREFIX) or Path(rel).name in IMPLEMENTATION:
            continue
        seen.add(name)
        stack.extend(_imported(ast.parse(files[rel]), known))
    return {known[name] for name in seen}


# --- (ii) every write call has a row with an output kind ----------------------------------


def rule_rows(files: Mapping[str, str], rows: list[Row]) -> list[str]:
    reached = run_reached(files)
    sinks = collect({rel: files[rel] for rel in reached}, OUTPUT_PRIMITIVES)
    live = {s.key for s in sinks}
    by_key = {r.key: r for r in rows if r.file in reached or r.disposition == ENTRY}
    out = [f"O1: write call with no row: {k}" for k in sorted(live - by_key.keys())]
    for key, row in sorted(by_key.items()):
        if row.disposition == ENTRY and not is_entry_row(row):
            out.append(f"O1: entry row is not structurally valid: {key}")
        elif row.disposition == ENTRY and row.file not in reached:
            out.append(f"O1: entry row outside the run-reached modules: {key}")
        elif key not in live:
            out.append(f"O1: row with no live write call: {key}")
        elif row.output_kind not in KINDS:
            out.append(f"O1: row with no valid output_kind ({row.output_kind!r}): {key}")
    return out


def test_every_write_call_in_a_run_reached_module_has_a_kind() -> None:
    assert rule_rows(live_files(), ROWS) == []


def test_the_closure_is_computed_and_follows_function_local_imports() -> None:
    files = {
        "cli/run/__init__.py": "def go():\n    from decoy.cli.later import f\n    f()\n",
        "cli/later.py": "def f():\n    pass\n",
        "cli/other.py": "x = 1\n",
        "cli/library/_fs.py": "x = 1\n",
    }
    assert run_reached(files) == {"cli/run/__init__.py", "cli/later.py"}
    assert "cli/io/_run_outputs.py" in run_reached(live_files())
    assert not any(rel.startswith(LIBRARY_PREFIX) for rel in run_reached(live_files()))


def test_a_new_write_call_with_no_row_is_red() -> None:
    """MO-sink-unlisted: a run-reached module gains a `write_local_target` call."""
    files = {
        **live_files(),
        "cli/run/_extra.py": (
            "from decoy._atomic import write_local_target\n"
            "def write(p):\n    write_local_target(p, b'x')\n"
        ),
        "cli/run/__init__.py": live_files()["cli/run/__init__.py"]
        + "\nfrom decoy.cli.run import _extra\n",
    }
    found = rule_rows(files, ROWS)
    assert found == ["O1: write call with no row: cli/run/_extra.py::write::write_local_target::1"]


def test_a_bad_row_is_red() -> None:
    first = next(r for r in ROWS if r.output_kind and r.disposition != ENTRY)
    kinds = [Row(**{**first.__dict__, "output_kind": "bogus"}) if r is first else r for r in ROWS]
    assert rule_rows(live_files(), kinds) == [
        f"O1: row with no valid output_kind ('bogus'): {first.key}"
    ]
    missing = [Row(**{**first.__dict__, "output_kind": ""}) if r is first else r for r in ROWS]
    assert len(rule_rows(live_files(), missing)) == 1


def test_an_entry_row_needs_a_live_sink_in_the_closure() -> None:
    ghost = Row(
        "cli/run/_result.py", "nowhere", "write_local_target", 1, ENTRY, "x", output_kind="result"
    )
    assert rule_rows(live_files(), [*ROWS, ghost]) == [
        f"O1: row with no live write call: {ghost.key}"
    ]
    outside = Row("ci/debug.py", "f", "mkdir", 1, ENTRY, "x", output_kind=NOT_RUN)
    assert any("outside the run-reached" in f for f in rule_rows(live_files(), [*ROWS, outside]))
    odd = Row("cli/run/_result.py", "f", "os.open", 1, ENTRY, "x", output_kind="result")
    assert any("not structurally valid" in f for f in rule_rows(live_files(), [*ROWS, odd]))
    assert "write_local_target" in PRIVATE_ENTRY


# --- (iii) one source of outputs, one report name -----------------------------------------


def _function(path: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((SRC / path).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_the_collision_rule_reads_only_the_inventory() -> None:
    body = _function("cli/io/_placement.py", "resolved_output_collisions")
    called = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(body)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    assert not called & {"relative_outputs", "report_file", "implicit_report_path"}
    assert not [n for n in ast.walk(body) if isinstance(n, ast.Attribute) and n.attr == "typed"]


def test_the_default_report_name_has_one_derivation() -> None:
    sites: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
                name = (
                    call.func.id
                    if isinstance(call.func, ast.Name)
                    else getattr(call.func, "attr", "")
                )
                first = call.args[0] if call.args else None
                if (
                    name == "side_file_name"
                    and isinstance(first, ast.Constant)
                    and first.value == "post_scan"
                ):
                    sites.append(f"{path.relative_to(SRC).as_posix()}::{fn.name}")
    assert sites == ["cli/io/_run_outputs.py::implicit_report_path"]


# --- (iv) the write audit -----------------------------------------------------------------

runner = CliRunner()


def _pipeline(root: Path, *, post_scan: bool, vault: bool, quarantine: bool) -> Path:
    path = root / "pipelines" / "customers.yaml"
    path.parent.mkdir(parents=True)
    src = root / "in.csv"
    src.write_text("id,email\n1,a@x.com\n2,b@y.com\n", encoding="utf-8")
    email: dict = {"name": "email", "strategy": "hash", "namespace": "em"}
    if vault:
        email["vault"] = True
    config: dict = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source(src)},
        "tables": [
            {"name": "people", "columns": [{"name": "id", "strategy": "passthrough"}, email]}
        ],
        "targets": {"people": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    if post_scan:
        config["post_scan"] = {"integrity": True}
    if quarantine:
        config["quarantine"] = {"enabled": True, "output_path": "quarantine.csv"}
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _lstat_tree(top: Path, skip: Path) -> dict[str, tuple]:
    seen: dict[str, tuple] = {}
    for folder, dirs, names in os.walk(top):
        if Path(folder) == skip:
            dirs[:] = []
            continue
        for name in [*dirs, *names]:
            path = Path(folder) / name
            if path == skip:
                continue
            info = os.lstat(path)
            seen[str(path)] = (info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino)
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
    return seen


def _allowed(
    config: Path, typed: tuple, out_dir: Path | None, root: Path, chunked: bool
) -> set[str]:
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    if out_dir is not None:
        placement = OutputPlacement.fixed(out_dir, typed, chunked)
        base: Path | None = out_dir
    else:
        placement = OutputPlacement(typed=typed, chunked=chunked)
        (run,) = [
            p for p in (root / "out" / "customers").iterdir() if p.is_dir() and not p.is_symlink()
        ]
        base = run
    # The library root is outside the audit; its folder above it changes when it is made.
    allowed: set[str] = {str(p) for p in (root / ".decoy", *(root / ".decoy").parents)}
    for out in run_outputs(raw, placement, config, base):
        allowed.update(str(p) for p in (out.path, *out.path.parents))
    return allowed


CASES = {
    "all-implicit": dict(
        flags=["--vault", "--evidence-out", "--result"], post_scan=True, vault=True
    ),
    "all-explicit": dict(
        flags=["--vault", "--evidence-out", "--result", "--integrity-out"],
        post_scan=True,
        vault=True,
    ),
    "chunked": dict(flags=["--chunked"], post_scan=False, vault=False),
    "out-dir": dict(flags=["--out-dir"], post_scan=True, vault=False),
}


@pytest.mark.skipif(os.name == "nt", reason="the audit walks POSIX links")
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_run_writes_only_what_run_outputs_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    spec = CASES[case]
    top = tmp_path.resolve()
    root = top / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    config = _pipeline(
        root,
        post_scan=spec["post_scan"],
        vault=spec["vault"],
        quarantine="--chunked" not in spec["flags"],
    )
    side = top / "side"
    side.mkdir()
    paths = {
        "--vault": side / "vault.bin",
        "--evidence-out": side / "evidence.json",
        "--result": side / "result.json",
        "--integrity-out": side / "integrity.json",
    }
    args: list[str] = []
    typed: list[tuple[str, Path]] = []
    out_dir: Path | None = None
    for flag in spec["flags"]:
        if flag == "--chunked":
            args.append(flag)
        elif flag == "--out-dir":
            out_dir = top / "build"
            args += [flag, str(out_dir)]
        else:
            args += [flag, str(paths[flag])]
            typed.append((flag, paths[flag]))
    monkeypatch.chdir(root)
    before = _lstat_tree(top, root / ".decoy")
    result = runner.invoke(app, ["run", str(config), *args])
    assert result.exit_code == 0, result.output
    after = _lstat_tree(top, root / ".decoy")
    allowed = _allowed(config, tuple(typed), out_dir, root, "--chunked" in args)
    changed = sorted(p for p, info in after.items() if before.get(p) != info)
    assert [p for p in changed if p not in allowed] == []
    # The audit sees something: the outputs the case asked for are among the changes.
    assert any(p.endswith("masked.csv") for p in changed), changed
