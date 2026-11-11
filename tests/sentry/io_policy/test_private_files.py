"""G-ONE-PRIVATE-FILE: every CLI file write is classified, and private ones go through one helper.

Walks every module under `src/decoy/` with the shared scanner (`_calls.py`) and enforces the same
rule numbers as the engine's `tests/sentry/test_private_files.py` (X7b). The CLI P4 is stricter
than the engine's: it covers `fchmod` too, because the CLI has one module that applies modes
(`src/decoy/_private_file.py`, the WIN-FEAS seam).

- P1: every watched sink, at every one-based call ordinal in source order, has a row in
  `file_sinks.toml` (file, qualified function, sink kind, ordinal); every row has that exact live
  sink; the disposition is one of public, private, staged, read, temp; the reason is non-empty.
  Private entry-point calls (`write_atomic`, `write_local_target`, `staged_private_target`,
  `write_private_table`, `open_private`, `create_private_temp`) need no row.
- P1b: `PRIVATE_CASES` maps every private entry-point call and every `via` row to a test in
  `tests/e2e/private_file/test_private_surfaces.py` or `tests/unit/private_file/`, both ways.
- P2: a raw sink with disposition `private` passes only when its `via` entry point is called
  earlier in the same function and the sink's path argument is the same local name as that call's
  path argument or result. A `temp` row, or a private row that fails the binding, must carry an
  `exit` and sit in `tests/sentry/baselines/private-file-sinks.json` (shrink-only).
- P3: no mode call in a `try` body whose handler only passes, and none under `suppress(...)`.
- P4: no mode call outside `_private_file.py`, except the launcher shim's `os.chmod(..., 0o755)`.
- P5: `_private_file.py` imports nothing from `decoy`.

A `public` row is a review item: its reason says why the bytes may be world-readable, and a wrong
`public` is not caught here. A `staged` row is accepted only in `cli/io/_targets.py` and only in a
function G-ONE-TARGET-WRITE checks (`STAGED_WRITERS`, imported from it): there, every path written
must be the temp a stager yields, and every caller must pass a real stager.

Named limits: P2's `via` check is source order in one function, not that the entry point runs on
every path. SQL other than `COPY ... TO`, SQL held in a variable, and `.sql()`, `duckdb.sql()` and
`executemany` calls are not seen. A reference through a runtime-bound name, an alias by
assignment, `from x import *`, a relative import (`bindings` in `_calls.py` skips it; ruff TID252
bans relative imports repo-wide), and calls that create no regular-file content (`os.link`,
`os.symlink`, `mkdir`, `shutil.rmtree`) are not seen either.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import (
    PATH_SLOT,
    Site,
    is_staged_name,
    leaf,
    path_arg,
    qualified,
    sites,
)
from tests.sentry.io_policy.test_target_writes import STAGE_CALLS, STAGED_WRITERS

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
HERE = Path(__file__).resolve().parent
ROWS_FILE = HERE / "file_sinks.toml"
BASELINE_FILE = ROOT / "tests" / "sentry" / "baselines" / "private-file-sinks.json"
CHOKE_POINT = "_private_file.py"
IMPLEMENTATION = frozenset({"_atomic.py", CHOKE_POINT})
STAGED_FILE = "cli/io/_targets.py"
DISPOSITIONS = frozenset({"public", "private", "staged", "read", "temp"})

PRIVATE_ENTRY = frozenset(
    {
        "write_atomic",
        "write_local_target",
        "staged_private_target",
        "write_private_table",
        "open_private",
        "create_private_temp",
        "create_private_directory",
    }
)
# Public entry points and raw sinks matched by the last name of the callee on any receiver.
_LEAF = frozenset(
    {
        "write_text", "write_bytes", "to_csv", "to_parquet", "write_table", "ParquetWriter",
        "write_to_dataset", "write_dataset", "write_csv", "CSVWriter", "write_fixed_width",
        "extractall", "staged_local_target", "chmod", "lchmod",
    }
)  # fmt: skip
# Raw sinks matched by the dotted name a bound import resolves to.
_RESOLVED = frozenset({"os.open", "os.fdopen", "sqlite3.connect", "duckdb.connect"})
_RESOLVED_PREFIX = ("tempfile.",)
_COPY = ("shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.move")
_MODE_CALLS = frozenset({"os.chmod", "os.fchmod", "os.lchmod", "chmod", "lchmod"})
_MODE_LITERAL = re.compile(r"^[rwxabt+]+(:[a-z]+)?$")
_COPY_TO = re.compile(r"\bCOPY\b.*\bTO\b", re.IGNORECASE | re.DOTALL)
# The one mode call allowed outside the choke point: the launcher shim's 0755 (a script others
# run, so not private). The site is matched exactly and checked for staleness.
LAUNCHER_SHIM = "distribution/installer.py::_write_launcher_shim::os.chmod::1"
LAUNCHER_MODE = 0o755

# Call site (`file::function::sink::ordinal`) to the test that proves the surface is 0600.
_E2E = "e2e:test_private_surfaces.py::"
_UNIT = "unit:test_private_file.py::"
_SPOOL = _E2E + "test_mask_spool_is_private_while_it_exists"
_CI = _E2E + "test_ci_report_and_debug_log_are_private"
_FIT_SCAN = _E2E + "test_fit_and_scan_outputs_are_private"
_REPORT = _E2E + "test_report_writers_are_private"
_RESTORED = _E2E + "test_unmask_and_detokenize_outputs_are_private"
_VAULT = _E2E + "test_tokenize_vault_and_its_journal_are_private"
_LIBRARY = _UNIT + "test_library_files_and_folders_are_owner_only_under_umask_zero"
_LIBRARY_LOCK = _UNIT + "test_library_lock_and_ref_files_are_owner_only_under_umask_zero"
PRIVATE_CASES: dict[str, str] = {
    "api.py::_stage_source_entry::create_private_temp::1": _SPOOL,
    "api.py::_stage_source_entry::write_table::1": _SPOOL,
    "ci/debug.py::DebugSink.flush::write_local_target::1": _CI,
    "cli/ci.py::check::write_local_target::1": _CI,
    "cli/compile_explain.py::compile::write_local_target::1": _E2E
    + "test_compile_output_is_private_and_its_bytes_are_the_rendered_plan",
    "cli/fit.py::fit::write_local_target::1": _FIT_SCAN,
    "cli/scanning/_multi.py::run_scan::write_local_target::1": _FIT_SCAN,
    "cli/report.py::_write_out::write_local_target::1": _REPORT,
    "cli/report.py::_render::write_local_target::1": _REPORT,
    "cli/run/_evidence.py::write_evidence::write_local_target::1": _E2E
    + "test_run_vault_and_evidence_are_private",
    "cli/tokenize.py::detokenize::write_private_table::1": _RESTORED,
    "cli/unmask.py::unmask::write_private_table::1": _RESTORED,
    "cli/_token_vault.py::LocalTokenVault.__init__::open_private::1": _VAULT,
    "cli/_token_vault.py::LocalTokenVault.__init__::sqlite3.connect::1": _VAULT,
    "_resources.py::write_settings::write_atomic::1": _E2E + "test_setup_settings_file_is_private",
    "distribution/installer.py::check_document_freshness::write_atomic::1": _UNIT
    + "test_installer_trust_state_is_owner_only_under_umask_zero",
    "cli/io/_layout.py::create_run_folder::create_private_directory::1": _UNIT
    + "test_create_private_directory_is_0700_under_umask_000",
    "cli/io/_layout.py::prepare_out::write_local_target::1": _UNIT
    + "test_layout_files_are_owner_only_under_umask_zero",
    "cli/io/_layout.py::write_claim::write_atomic::1": _UNIT
    + "test_layout_files_are_owner_only_under_umask_zero",
    "cli/io/_layout.py::RunLayout.commit_latest::write_atomic::1": _UNIT
    + "test_layout_files_are_owner_only_under_umask_zero",
    "cli/io/_project.py::ensure_decoy_dir::write_local_target::1": _UNIT
    + "test_layout_files_are_owner_only_under_umask_zero",
    "cli/library/_fs.py::ensure_private_dir::create_private_directory::1": _LIBRARY,
    "cli/library/_fs.py::_write::write_atomic::1": _LIBRARY,
    "cli/library/_refs.py::library_lock::open_private::1": _LIBRARY_LOCK,
    "cli/library/_refs.py::library_lock::sqlite3.connect::1": _LIBRARY_LOCK,
    "cli/library/_fs.py::write_dotfile_once::write_local_target::1": _LIBRARY,
}
_CASE_MODULES = {
    "e2e:test_private_surfaces.py": ROOT / "tests/e2e/private_file/test_private_surfaces.py",
    "unit:test_private_file.py": ROOT / "tests/unit/private_file/test_private_file.py",
}


# --- registry rows ------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    file: str
    function: str
    sink: str
    ordinal: int
    disposition: str
    reason: str
    via: str = ""
    exit: str = ""

    @property
    def key(self) -> str:
        return f"{self.file}::{self.function}::{self.sink}::{self.ordinal}"


def load_rows(text: str) -> list[Row]:
    return [Row(**raw) for raw in tomllib.loads(text).get("row", [])]


ROWS = load_rows(ROWS_FILE.read_text(encoding="utf-8"))
# The shrink-only baseline source (`tests/sentry/_baseline_sources.py`): rows that carry an exit.
BASELINE_ROWS = tuple((r.key, r.reason) for r in ROWS if r.exit)


# --- the scan -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Sink:
    file: str
    function: str
    kind: str
    ordinal: int
    site: Site

    @property
    def key(self) -> str:
        return f"{self.file}::{self.function}::{self.kind}::{self.ordinal}"

    @property
    def call(self) -> ast.Call:
        assert isinstance(self.site.node, ast.Call)
        return self.site.node


def _sql_text(call: ast.Call) -> str:
    if not call.args:
        return ""
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        return " ".join(
            p.value for p in arg.values if isinstance(p, ast.Constant) and isinstance(p.value, str)
        )
    return ""


def _write_mode(call: ast.Call, *, builtin: bool) -> bool:
    """True when an `open` call can write: a mode string with w, a, x or +, or a mode unknown."""
    keyword = {k.arg: k.value for k in call.keywords if k.arg}
    if builtin:
        arg = keyword.get("mode") or (call.args[1] if len(call.args) > 1 else None)
        if arg is None:
            return False
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            return True  # a mode the walk cannot read is treated as a write
        return bool(set(arg.value) & set("wax+"))
    # `Path.open(mode)`, `gzip.open(path, mode)`, `tarfile.open(name, mode)`: only a constant
    # that looks like a mode counts, so `webbrowser.open("https://...")` is not a sink.
    candidates = [*call.args[:2], keyword.get("mode")]
    return any(
        isinstance(c, ast.Constant)
        and isinstance(c.value, str)
        and _MODE_LITERAL.fullmatch(c.value)
        and set(c.value) & set("wax+")
        for c in candidates
    )


def classify(site: Site) -> str | None:
    """The sink kind of a call, or None when the call is not watched."""
    call = site.node
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    resolved = site.name
    name = leaf(call, site.bound)  # the resolved member, so an import alias cannot hide a sink
    if resolved and resolved in _MODE_CALLS | _RESOLVED:
        return resolved
    if resolved and (resolved.startswith(_RESOLVED_PREFIX) or resolved in _COPY):
        return resolved
    if name in PRIVATE_ENTRY or name in _LEAF:
        return name
    if name == "open":
        return "open" if _write_mode(call, builtin=isinstance(func, ast.Name)) else None
    if name == "execute" and _COPY_TO.search(_sql_text(call)):
        return "execute.copy_to"
    return None


def collect(files: Mapping[str, str]) -> list[Sink]:
    """Every watched call in `files` (relative path to source), with one-based ordinals."""
    out: list[Sink] = []
    for rel in sorted(files):
        seen: dict[tuple[str, str], int] = {}
        for site in sites(ast.parse(files[rel]), with_calls=STAGE_CALLS):
            kind = classify(site)
            if kind is None:
                continue
            n = seen[(site.scope, kind)] = seen.get((site.scope, kind), 0) + 1
            out.append(Sink(rel, site.scope, kind, n, site))
    return out


def live_files() -> dict[str, str]:
    return {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(SRC.rglob("*.py"))
    }


def is_entry(s: Sink) -> bool:
    return s.kind in PRIVATE_ENTRY


def watched(all_sinks: list[Sink]) -> list[Sink]:
    """The sinks P1 covers: everything outside the implementation modules."""
    return [s for s in all_sinks if s.file not in IMPLEMENTATION]


# --- P1, P1b, P2 --------------------------------------------------------------------------


def _name(expr: ast.expr | None) -> str | None:
    """A dotted local name for a Name/Attribute chain after stripping str(), fspath(), Path()."""
    while isinstance(expr, ast.Call) and len(expr.args) == 1 and not expr.keywords:
        f = expr.func
        if (isinstance(f, ast.Name) and f.id in {"str", "Path"}) or (
            isinstance(f, ast.Attribute) and f.attr in {"fspath", "Path"}
        ):
            expr = expr.args[0]
        else:
            break
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "as_posix"
        and not expr.args
    ):
        expr = expr.func.value
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    return ".".join([expr.id, *reversed(parts)])


def sink_path_name(s: Sink) -> str | None:
    """The local name a raw sink writes to, or None when the walk cannot name it."""
    func = s.call.func
    if PATH_SLOT.get(s.kind, ...) is None:
        return _name(func.value) if isinstance(func, ast.Attribute) else None
    return _name(path_arg(s.call, s.kind))


def entry_names(entry: Sink) -> set[str]:
    """Names an entry-point call stands for: its first argument, and what it is bound to."""
    names: set[str] = set()
    first = _name(entry.call.args[0]) if entry.call.args else None
    if first:
        names.add(first)
    if entry.site.ancestors:
        parent, field = entry.site.ancestors[-1]
        if isinstance(parent, ast.withitem) and field == "context_expr":
            if isinstance(parent.optional_vars, ast.Name):
                names.add(parent.optional_vars.id)
        elif isinstance(parent, (ast.Assign, ast.AnnAssign)) and field == "value":
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            names.update(n for n in map(_name, targets) if n)
    return names


def _position(s: Sink) -> tuple[int, int]:
    return s.call.lineno, s.call.col_offset


def via_holds(sink: Sink, row: Row, all_sinks: list[Sink]) -> bool:
    """P2: the row's `via` entry point is called earlier in this function on the sink's path."""
    path = sink_path_name(sink)
    if not (row.via and path):
        return False
    return any(
        e.file == sink.file
        and e.site.scope == sink.site.scope
        and e.kind == row.via
        and _position(e) < _position(sink)
        and path in entry_names(e)
        for e in all_sinks
    )


def needs_baseline(sink: Sink, row: Row, all_sinks: list[Sink]) -> bool:
    if row.disposition == "temp":
        return True
    return row.disposition == "private" and not via_holds(sink, row, all_sinks)


def _live(all_sinks: list[Sink]) -> dict[str, Sink]:
    return {s.key: s for s in watched(all_sinks) if not is_entry(s)}


def _writes_stage_temp(sink: Sink) -> bool:
    """A staged sink writes the name an enclosing `with <stager>(...) as tmp` bound."""
    path = sink_path_name(sink)
    return path is not None and is_staged_name(ast.Name(id=path), sink.site.with_names)


def rule_p1(all_sinks: list[Sink], rows: list[Row]) -> list[str]:
    out: list[str] = []
    live = _live(all_sinks)
    by_key: dict[str, Row] = {}
    for r in rows:
        if r.key in by_key:
            out.append(f"P1: duplicate row {r.key}")
        by_key[r.key] = r
    out += [f"P1: sink with no row: {k}" for k in sorted(live.keys() - by_key.keys())]
    out += [f"P1: row with no live sink: {k}" for k in sorted(by_key.keys() - live.keys())]
    for r in rows:
        if r.disposition not in DISPOSITIONS:
            out.append(f"P1: bad disposition {r.disposition!r}: {r.key}")
        if not r.reason.strip():
            out.append(f"P1: empty reason: {r.key}")
        if r.ordinal < 1:
            out.append(f"P1: ordinal is one-based: {r.key}")
        if r.disposition == "staged" and (
            r.file != STAGED_FILE or r.function not in STAGED_WRITERS
        ):
            out.append(f"P1: staged row outside the checked stager writers: {r.key}")
        sink = live.get(r.key)
        if r.disposition == "staged" and sink is not None and not _writes_stage_temp(sink):
            out.append(f"P1: staged sink does not write the stager's temp path: {r.key}")
    return out


def rule_p2(all_sinks: list[Sink], rows: list[Row]) -> list[str]:
    out: list[str] = []
    live = _live(all_sinks)
    for r in rows:
        sink = live.get(r.key)
        if sink is None:
            continue  # reported by P1
        if r.via and r.disposition != "private":
            out.append(f"P2: only a private row has a via: {r.key}")
        if r.via and r.via not in PRIVATE_ENTRY:
            out.append(f"P2: via {r.via!r} is not a private entry point: {r.key}")
        needs = needs_baseline(sink, r, all_sinks)
        if needs and not r.exit:
            out.append(f"P2: private sink not bound to its entry point and not baselined: {r.key}")
        if r.exit and not needs:
            out.append(f"P2: row carries an exit but does not need the baseline: {r.key}")
    return out


def rule_p1b(all_sinks: list[Sink], rows: list[Row], cases: Mapping[str, str]) -> list[str]:
    wanted = {s.key for s in watched(all_sinks) if is_entry(s)}
    wanted |= {r.key for r in rows if r.disposition == "private" and r.via and not r.exit}
    out = [f"P1b: private site with no case: {k}" for k in sorted(wanted - cases.keys())]
    return out + [
        f"P1b: case with no live private site: {k}" for k in sorted(cases.keys() - wanted)
    ]


def case_test_names() -> set[str]:
    names: set[str] = set()
    for prefix, path in _CASE_MODULES.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names |= {
            f"{prefix}::{n.name}"
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        }
    return names


def rule_case_ids(cases: Mapping[str, str], tests: set[str]) -> list[str]:
    return [
        f"P1b: case id names no test: {k} -> {v}"
        for k, v in sorted(cases.items())
        if v not in tests
    ]


# --- P3, P4, P5 ---------------------------------------------------------------------------


def is_mode_call(s: Sink) -> bool:
    return s.kind in _MODE_CALLS


def _swallows(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(n, (ast.Pass, ast.Continue))
        or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is ...)
        for n in handler.body
    )


_TRY = (ast.Try, getattr(ast, "TryStar", ast.Try))


def _is_suppress(ctx: ast.Call, bound: Mapping[str, str]) -> bool:
    resolved = qualified(ctx, dict(bound))
    return resolved == "contextlib.suppress" if resolved else leaf(ctx, dict(bound)) == "suppress"


def swallowed(s: Sink) -> bool:
    """True when the call sits in a `try` body whose handler only passes, or under suppress()."""
    for node, field in s.site.guards():
        if isinstance(node, _TRY) and field == "body" and any(_swallows(h) for h in node.handlers):
            return True
        if isinstance(node, (ast.With, ast.AsyncWith)) and field == "items":
            continue
        if isinstance(node, (ast.With, ast.AsyncWith)) and field == "body":
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and _is_suppress(ctx, s.site.bound):
                    return True
    return False


def rule_p3(all_sinks: list[Sink]) -> list[str]:
    return [
        f"P3: mode change in a swallowed try: {s.key}"
        for s in all_sinks
        if is_mode_call(s) and swallowed(s)
    ]


def _launcher_mode_ok(s: Sink) -> bool:
    args = s.call.args
    return len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value == LAUNCHER_MODE


def rule_p4(all_sinks: list[Sink]) -> list[str]:
    out: list[str] = []
    seen_exception = False
    for s in all_sinks:
        if not is_mode_call(s) or s.file == CHOKE_POINT:
            continue
        if s.key == LAUNCHER_SHIM and _launcher_mode_ok(s):
            seen_exception = True
            continue
        out.append(f"P4: mode change outside {CHOKE_POINT}: {s.key}")
    if not seen_exception:
        out.append(f"P4: the launcher exception is stale (call or mode changed): {LAUNCHER_SHIM}")
    return out


def rule_p5(source: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out += [f"P5: imports {a.name}" for a in node.names if a.name.split(".")[0] == "decoy"]
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] == "decoy":
                out.append(f"P5: imports from {'.' * node.level}{node.module or ''}")
    return out


# --- the baseline -------------------------------------------------------------------------


def baseline_entries(rows: list[Row]) -> dict[str, dict[str, str]]:
    return {r.key: {"reason": r.reason, "exit": r.exit} for r in rows if r.exit}


def rule_baseline(rows: list[Row], recorded: Mapping[str, object]) -> list[str]:
    derived = baseline_entries(rows)
    out = [
        f"baseline: key not derived from a row that needs it: {k}"
        for k in sorted(recorded.keys() - derived.keys())
    ]
    out += [f"baseline: missing key: {k}" for k in sorted(derived.keys() - recorded.keys())]
    out += [
        f"baseline: entry differs from its row: {k}"
        for k in sorted(derived.keys() & recorded.keys())
        if recorded[k] != derived[k]
    ]
    return out


def all_findings(
    files: Mapping[str, str],
    rows: list[Row],
    recorded: Mapping[str, object],
    cases: Mapping[str, str],
    tests: set[str],
) -> list[str]:
    sinks = collect(files)
    out = rule_p1(sinks, rows) + rule_p2(sinks, rows) + rule_p1b(sinks, rows, cases)
    out += rule_case_ids(cases, tests) + rule_p3(sinks) + rule_p4(sinks)
    if CHOKE_POINT in files:
        out += rule_p5(files[CHOKE_POINT])
    return out + rule_baseline(rows, recorded)


def recorded_baseline() -> dict[str, object]:
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))["entries"]


# --- tests: the live tree -----------------------------------------------------------------


@pytest.fixture(scope="module")
def files() -> dict[str, str]:
    return live_files()


def run(source_files: Mapping[str, str], **given: object) -> list[str]:
    return all_findings(
        source_files,
        given.get("rows", ROWS),  # type: ignore[arg-type]
        given.get("recorded", recorded_baseline()),  # type: ignore[arg-type]
        given.get("cases", PRIVATE_CASES),  # type: ignore[arg-type]
        given.get("tests", case_test_names()),  # type: ignore[arg-type]
    )


def test_the_live_tree_is_clean(files: dict[str, str]) -> None:
    """AT-P2j: P1 to P5 hold with the 5-row baseline, and every private site has a case."""
    assert run(files) == []


def test_the_census_is_60_watched_sinks(files: dict[str, str]) -> None:
    sinks = watched(collect(files))
    assert len(sinks) == 60
    assert len([s for s in sinks if is_entry(s)]) == 23
    counts: dict[str, int] = {}
    for r in ROWS:
        counts[r.disposition] = counts.get(r.disposition, 0) + 1
    assert counts == {"public": 23, "private": 5, "staged": 3, "temp": 3, "read": 3}


def test_the_baseline_has_five_rows_with_exits() -> None:
    doc = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    assert doc["sentry_id"] == "private-file-sinks"
    assert doc["created_in"] == "X7c-S3"
    assert len(doc["entries"]) == 5
    assert all(e["exit"] for e in doc["entries"].values())
    assert doc["entries"] == baseline_entries(ROWS)


# --- tests: seeded violations (AT-P2a to AT-P2l), each must go red ------------------------

NEW = "newmod.py"


def _row(function: str, sink: str, ordinal: int = 1, **kw: str) -> Row:
    values = {"disposition": "public", "reason": "seeded row for the sentry's own test"} | kw
    return Row(NEW, function, sink, ordinal, **values)


def seeded(source: str, *, rows: list[Row] | None = None, **given: object) -> list[str]:
    return run({**live_files(), NEW: source}, **{"rows": [*ROWS, *(rows or [])], **given})


def _has(findings: list[str], *needles: str) -> bool:
    return any(all(n in f for n in needles) for f in findings)


def test_seed_a_attribute_path_write_bytes_with_no_row() -> None:
    src = "def f(settings, v):\n    path = settings.key_path\n    path.write_bytes(v)\n"
    assert _has(seeded(src), "P1", "sink with no row", f"{NEW}::f::write_bytes::1")


def test_seed_b_path_built_from_config_write_text_with_no_row() -> None:
    src = "def f(cfg, name, v):\n    p = Path(cfg.key_dir) / name\n    p.write_text(v)\n"
    assert _has(seeded(src), "P1", f"{NEW}::f::write_text::1")


def test_seed_c_private_row_whose_via_call_is_absent() -> None:
    src = 'def f(target):\n    with open(target, "wb") as h:\n        h.write(b"")\n'
    findings = seeded(src, rows=[_row("f", "open", disposition="private", via="open_private")])
    assert _has(findings, "P2", "not bound to its entry point", f"{NEW}::f::open::1")


def test_seed_c_a_via_call_on_a_different_name_does_not_bind() -> None:
    src = (
        "from decoy._private_file import open_private\n"
        "def f(a, b):\n    open_private(a, new_parent=False)\n    open(b, 'wb')\n"
    )
    findings = seeded(src, rows=[_row("f", "open", disposition="private", via="open_private")])
    assert _has(findings, "P2", f"{NEW}::f::open::1")


def test_a_bound_via_row_passes_without_a_baseline_entry() -> None:
    src = (
        "from decoy._private_file import open_private\n"
        "def f(path):\n    open_private(path, new_parent=False)\n    open(str(path), 'wb')\n"
    )
    findings = seeded(src, rows=[_row("f", "open", disposition="private", via="open_private")])
    # The entry-point call has no case here, which P1b reports; P1 and P2 are clean.
    assert [f for f in findings if f.startswith(("P1:", "P2:"))] == []


def test_seed_d_chmod_in_a_try_whose_handler_passes() -> None:
    src = "import os\ndef f(p):\n    try:\n        os.chmod(p, 0o600)\n    except OSError:\n        pass\n"
    assert _has(seeded(src), "P3", f"{NEW}::f::os.chmod::1")


def test_seed_d_suppress_is_a_swallowed_try_too() -> None:
    src = (
        "import os, contextlib\ndef f(p):\n"
        "    with contextlib.suppress(OSError):\n        os.fchmod(p, 0o600)\n"
    )
    assert _has(seeded(src), "P3", f"{NEW}::f::os.fchmod::1")


def test_p3_ignores_a_call_in_the_handler_else_or_finally() -> None:
    src = (
        "import os\ndef f(p):\n    try:\n        pass\n    except OSError:\n        pass\n"
        "    else:\n        os.chmod(p, 0o600)\n    finally:\n        os.chmod(p, 0o600)\n"
    )
    assert not _has(seeded(src), "P3")


def test_p3_does_not_blame_a_nested_function_for_the_outer_try() -> None:
    src = (
        "import os\ndef f(p):\n    try:\n        def g():\n            os.chmod(p, 0o600)\n"
        "    except OSError:\n        pass\n"
    )
    assert not _has(seeded(src), "P3")


def test_seed_e_chmod_outside_the_choke_point() -> None:
    findings = seeded("import os\ndef f(p):\n    os.chmod(p, 0o600)\n")
    assert _has(findings, "P4", f"{NEW}::f::os.chmod::1")


def test_seed_f_aliased_import_of_chmod() -> None:
    src = "from os import chmod as c\ndef f(p, mode):\n    c(p, mode)\n"
    assert _has(seeded(src), "P4", f"{NEW}::f::os.chmod::1")


def test_seed_k_a_new_inline_0700_chmod_outside_the_choke_point() -> None:
    assert _has(seeded("import os\ndef f(p):\n    os.chmod(p, 0o700)\n"), "P4")


def test_the_launcher_exception_is_exact_and_stale_checked(files: dict[str, str]) -> None:
    rel = "distribution/installer.py"
    call = "os.chmod(tmp, 0o755)"
    assert call in files[rel]
    for changed in (
        files[rel].replace(call, "os.chmod(tmp, 0o711)"),
        files[rel].replace(call, f"{call}\n        os.chmod(tmp, 0o755)"),
        files[rel].replace(call, "pass"),
    ):
        assert _has(run({**files, rel: changed}), "P4")


def test_seed_g_a_registry_row_whose_sink_is_gone() -> None:
    findings = seeded("x = 1\n", rows=[_row("f", "write_text")])
    assert _has(findings, "P1", "row with no live sink", f"{NEW}::f::write_text::1")


def test_seed_h_a_baseline_key_added() -> None:
    added = {"x.py::f::write_text::1": {"reason": "r" * 20, "exit": "X"}}
    recorded = {**recorded_baseline(), **added}
    assert _has(run(live_files(), recorded=recorded), "baseline", "x.py::f::write_text::1")


def test_a_baseline_entry_cannot_differ_from_its_row() -> None:
    recorded = {k: {**v, "exit": "elsewhere"} for k, v in baseline_entries(ROWS).items()}
    assert _has(run(live_files(), recorded=recorded), "baseline: entry differs")


def test_seed_i_duckdb_copy_to_with_no_row() -> None:
    src = "def f(conn, dest):\n    conn.execute(f\"copy t to '{dest}'\")\n"
    assert _has(seeded(src), "P1", f"{NEW}::f::execute.copy_to::1")


def test_a_select_is_not_a_copy_sink() -> None:
    assert not _has(seeded("def f(c):\n    c.execute('SELECT 1')\n"), "P1")


def test_seed_j_a_second_same_kind_sink_in_a_registered_function() -> None:
    src = "def f(p):\n    p.write_text('a')\n    p.write_text('b')\n"
    findings = seeded(src, rows=[_row("f", "write_text")])
    assert _has(findings, "P1", "sink with no row", f"{NEW}::f::write_text::2")
    assert not _has(findings, f"{NEW}::f::write_text::1")


def test_seed_l_the_choke_point_imports_from_decoy() -> None:
    assert rule_p5("from decoy._atomic import x\n") == ["P5: imports from decoy._atomic"]
    assert rule_p5("import decoy\n") == ["P5: imports decoy"]
    assert rule_p5("from . import x\n") == ["P5: imports from ."]
    assert rule_p5("import os\nfrom pathlib import Path\n") == []
    live = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    assert _has(run({**live_files(), CHOKE_POINT: live + "\nimport decoy\n"}), "P5")


def test_a_disposition_outside_the_five_and_an_empty_reason_fail() -> None:
    findings = seeded(
        "def f(p):\n    p.write_text('a')\n",
        rows=[_row("f", "write_text", disposition="secret", reason="")],
    )
    assert _has(findings, "P1", "bad disposition") and _has(findings, "P1", "empty reason")


def test_a_staged_row_for_a_new_module_is_refused() -> None:
    src = "def f(p):\n    p.write_text('a')\n"
    findings = seeded(src, rows=[_row("f", "write_text", disposition="staged")])
    assert _has(findings, "P1", "staged row outside", f"{NEW}::f::write_text::1")


def test_a_staged_row_in_an_unchecked_function_of_the_writer_module_is_refused() -> None:
    row = Row(
        STAGED_FILE, "write_targets", "write_table", 1, "staged", "seeded row for the sentry's test"
    )
    rows = [r for r in ROWS if r.key != row.key] + [row]
    assert _has(run(live_files(), rows=rows), "P1", "staged row outside", row.key)


def test_a_temp_row_without_an_exit_is_refused() -> None:
    src = "import tempfile\ndef f():\n    return tempfile.mkdtemp()\n"
    findings = seeded(src, rows=[_row("f", "tempfile.mkdtemp", disposition="temp")])
    assert _has(findings, "P2", f"{NEW}::f::tempfile.mkdtemp::1")


def test_a_read_only_open_is_not_a_sink() -> None:
    assert not _has(seeded("def f(p):\n    return open(p).read()\n"), "P1")
    assert not _has(seeded("def f(p):\n    return p.open('rb').read()\n"), "P1")


def test_a_writing_open_is_a_sink() -> None:
    assert _has(seeded("def f(p):\n    return open(p, 'wb')\n"), "P1", f"{NEW}::f::open::1")
    assert _has(seeded("def f(p, m):\n    return open(p, m)\n"), "P1", f"{NEW}::f::open::1")
    assert _has(seeded("def f(p):\n    return p.open('w')\n"), "P1", f"{NEW}::f::open::1")


_ENTRY_SRC = (
    "from decoy._atomic import write_local_target\n"
    "def f(p, d):\n    write_local_target(p, d, None)\n"
)


def test_seed_p1b_a_new_private_entry_call_with_no_case() -> None:
    findings = seeded(_ENTRY_SRC)
    assert _has(findings, "P1b", "private site with no case", f"{NEW}::f::write_local_target::1")


def test_seed_p1b_a_case_for_a_site_that_is_gone() -> None:
    cases = {**PRIVATE_CASES, f"{NEW}::f::write_local_target::1": _SPOOL}
    assert _has(seeded("x = 1\n", cases=cases), "P1b", "case with no live private site")


def test_seed_p1b_a_case_id_that_names_no_test() -> None:
    key = next(iter(PRIVATE_CASES))
    cases = {**PRIVATE_CASES, key: _E2E + "test_nothing_here"}
    assert _has(run(live_files(), cases=cases), "P1b", "case id names no test", key)


def test_every_case_id_names_a_real_test() -> None:
    assert rule_case_ids(PRIVATE_CASES, case_test_names()) == []


def test_entry_point_calls_need_no_row() -> None:
    cases = {**PRIVATE_CASES, f"{NEW}::f::write_local_target::1": _SPOOL}
    findings = seeded(_ENTRY_SRC, cases=cases)
    assert [f for f in findings if f.startswith(("P1:", "P1b:"))] == []
