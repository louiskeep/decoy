"""Build-failing sentry, part 2: runtime containment, write exclusivity and canaries.

1. Containment. The boundary restores `warnings.filters`, the logging threshold, the
   root handlers and the process streams exactly, under nesting and under
   overlapping threads; after EVERY CLI invocation below the same is asserted.
2. Write exclusivity. An audit hook (file opens for writing) and an `os.write`
   wrapper prove that no file or fd write during an invocation originates from a
   command module, the projections or the engine -- only `_boundary.py` writes --
   regardless of how the write is spelled. Seeded writes prove the audit bites.
3. Canaries. Distinct tokens are seeded into a source path, a table name, invalid
   layout values, every free-text, identifier, flag and number field of the engine
   reports, engine exception messages (including `SystemExit("...")` and dynamically
   named exception classes), warnings (including dynamically named categories and a
   warning raised inside `PipelineConfig.model_validate`), log records (including
   level 60, above CRITICAL), stray `print`/stderr writes, and the `--report-out`,
   `--output` and `--debug-log` paths. Every surface -- stdout, stderr, the JSON
   envelope, written files, pre-installed log handlers, `--verbose` -- is scanned
   across pre-scan (and fields/show/diff), post-scan integrity and post-scan
   fidelity, on success and error paths, and every scan first asserts its surface
   was NON-EMPTY so an empty stream can never pass vacuously.

Policy the canaries respect by design: a short clean-charset COLUMN name is schema
and is printed (same rule as the platform's `fidelity-report/v1`), so column
canaries here use characters a column name policy must reject. Table names are
always opaque, so the table canary is clean-charset on purpose. The pre-scan
`--output FILE` saved scan is the one explicit raw artifact: it may hold cell
values, but never a path, exception text or layout value, and it is mode 0600.
"""

from __future__ import annotations

import json as _json
import logging
import os
import sys
import threading
import warnings
from pathlib import Path
from typing import Any

import decoy_engine
import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import _boundary as bd

runner = CliRunner()
CLI_SRC = str(Path(bd.__file__).resolve().parent)
ENGINE_SRC = str(Path(decoy_engine.__file__).resolve().parent)
BOUNDARY_FILE = str(Path(bd.__file__).resolve())

PATH = "QZPATH5180"
TABLE = "QZTABLE6291"
LAYOUT_NUM = "7302914856"
LAYOUT_TXT = "QZLAYOUT4417"
ENGINE = "QZENGINE8823"
EXC = "QZEXC1937"
WARN = "QZWARN2046"
REPORT = "QZREPORT3375"
DEBUG = "QZDEBUG5591"
CELL = "QZCELL9904"
CANARIES = (PATH, TABLE, LAYOUT_NUM, LAYOUT_TXT, ENGINE, EXC, WARN, REPORT, DEBUG, CELL)
DIRTY_COL = f"/var/{ENGINE}/col"
MODES = {"text": [], "json": ["--json"], "verbose": ["-v"], "quiet": ["-q"]}


# ---------------------------------------------------------------------------
# Write audit: only the boundary may open a file for writing or write an fd.
# ---------------------------------------------------------------------------

_AUDIT: dict[str, Any] = {"on": False, "violations": []}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _origin(frame: Any) -> str | None:
    """The nearest CLI or engine source file on the stack."""
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith((CLI_SRC, ENGINE_SRC)):
            return name
        frame = frame.f_back
    return None


def _note_write(what: str, frame: Any) -> None:
    origin = _origin(frame)
    if origin is not None and origin != BOUNDARY_FILE:
        _AUDIT["violations"].append((what, origin))


def _audit_hook(event: str, args: tuple[Any, ...]) -> None:
    if not _AUDIT["on"] or event != "open":
        return
    path, mode, flags = args
    # Bytecode caches are the import system's, not a surface.
    if "__pycache__" in str(path):
        return
    writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
        isinstance(flags, int) and flags & _WRITE_FLAGS
    )
    if writing:
        _note_write(f"open({mode or flags})", sys._getframe(1))


sys.addaudithook(_audit_hook)
_real_os_write = os.write


def _audited_os_write(fd: int, data: Any) -> int:
    if _AUDIT["on"]:
        if fd in (1, 2):
            _AUDIT["violations"].append(("os.write to fd 1/2", _origin(sys._getframe(1))))
        else:
            _note_write("os.write", sys._getframe(1))
    return _real_os_write(fd, data)


@pytest.fixture(autouse=True)
def _write_audit(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(os, "write", _audited_os_write)
    _AUDIT["violations"] = []
    yield
    _AUDIT["on"] = False


def _snapshot() -> tuple[Any, ...]:
    return (
        list(warnings.filters),
        logging.root.manager.disable,
        list(logging.root.handlers),
        list(logging.getLogger("decoy_engine").handlers),
        sys.stdout,
        sys.stderr,
    )


def _invoke(argv: list[str], **kw: Any) -> Any:
    """Every invocation: write-audited, and process state must come back unchanged."""
    before = _snapshot()
    _AUDIT["on"] = True
    try:
        result = runner.invoke(app, argv, **kw)
    finally:
        _AUDIT["on"] = False
    assert _snapshot() == before, "the boundary leaked process state"
    assert not _AUDIT["violations"], _AUDIT["violations"]
    return result


# ---------------------------------------------------------------------------
# Pre-installed handlers: a record reaching one is a leak whatever its text.
# ---------------------------------------------------------------------------


class _Spy(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=1)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def spies() -> Any:
    root_spy, engine_spy = _Spy(), _Spy()
    logging.getLogger().addHandler(root_spy)
    logging.getLogger("decoy_engine").addHandler(engine_spy)
    yield root_spy, engine_spy
    logging.getLogger().removeHandler(root_spy)
    logging.getLogger("decoy_engine").removeHandler(engine_spy)
    assert not root_spy.records and not engine_spy.records, "a log record reached a handler"


# ---------------------------------------------------------------------------
# Fixtures and the surface scan.
# ---------------------------------------------------------------------------


@pytest.fixture
def work(tmp_path: Path) -> Path:
    d = tmp_path / f"d_{PATH}"
    d.mkdir()
    return d


@pytest.fixture
def source(work: Path) -> Path:
    p = work / f"src_{PATH}.csv"
    pd.DataFrame(
        {
            "email": [CELL] * 6 + ["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            "n": list(range(10)),
        }
    ).to_csv(p, index=False)
    return p


@pytest.fixture
def masked(work: Path, source: Path) -> Path:
    # The file stem would become the table name if the CLI derived one from it.
    p = work / f"{TABLE}.csv"
    p.write_text(source.read_text())
    return p


def _scan(
    result: Any,
    caplog: Any,
    *files: Path,
    mode: str,
    ok: bool,
    raw_artifacts: tuple[Path, ...] = (),
    streamed: bool = False,
    expect_debug: bool = False,
) -> None:
    """Assert the expected surface is NON-EMPTY, then that no canary is on any surface.

    `raw_artifacts` (the pre-scan saved scan) may hold engine profile content and cell
    values; never a path, table label, exception, layout value or warning.
    """
    stdout, stderr = result.stdout or "", result.stderr or ""
    if streamed or mode == "json":
        payload = _json.loads(stdout)
        assert payload.get("schema_version") or payload.get("code"), stdout
        if not ok:
            assert payload["status"] == "error" and payload["code"], payload
    elif ok and mode in ("text", "verbose"):
        assert stdout.strip(), "expected a non-empty stdout surface"
    elif ok and mode == "quiet":
        assert stdout == "", stdout
    if not ok and mode != "json":
        assert stderr.strip(), "expected a non-empty stderr surface"
    if expect_debug and mode == "verbose":
        assert "engine warning(s) withheld" in stderr, stderr
    parts = [stdout, stderr]
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        parts.append(f"UNCAUGHT {type(result.exception).__name__}: {result.exception}")
    parts.extend(r.getMessage() for r in caplog.records)
    text = "\n".join(parts)
    for canary in CANARIES:
        assert canary not in text, f"{canary} leaked to a stream/log:\n{text}"
    assert "Traceback" not in text
    for f in files:
        assert f.exists() and f.stat().st_size > 0, f"expected written file {f.name}"
        body = f.read_text(encoding="utf-8", errors="replace")
        for canary in CANARIES:
            if canary in (CELL, ENGINE) and f in raw_artifacts:
                continue
            assert canary not in body, f"{canary} leaked into written file {f.name}"
    for f in raw_artifacts:
        assert (f.stat().st_mode & 0o777) == 0o600, oct(f.stat().st_mode)
    assert not (result.exception is not None and not isinstance(result.exception, SystemExit))


# ---------------------------------------------------------------------------
# Engine stand-ins.
# ---------------------------------------------------------------------------

_DynWarn = type(f"Warn_{WARN}_{CELL}", (UserWarning,), {})
_CALLS: list[str] = []


def _noisy(fn: Any) -> Any:
    """Engine stand-in that also warns, logs, prints and writes stderr with canaries."""

    def wrapper(*a: Any, **k: Any) -> Any:
        _CALLS.append(fn.__name__)
        warnings.warn(f"engine says {WARN} {CELL}", UserWarning, stacklevel=1)
        warnings.warn(f"dyn {CELL}", _DynWarn, stacklevel=1)
        logging.getLogger("decoy_engine.x").warning("engine log %s %s", WARN, TABLE)
        logging.getLogger("decoy_engine").log(60, f"HIGH_LOG {WARN} {CELL}")
        logging.getLogger().log(1000, f"VERY_HIGH_LOG {CELL}")
        logging.getLogger().error("root log %s", WARN)
        print(f"PRINT {CELL}")
        sys.stderr.write(f"STDERR {CELL}\n")
        return fn(*a, **k)

    return wrapper


def _poisoned_integrity(*_a: Any, **_k: Any) -> dict[str, Any]:
    finding = {
        "table": TABLE,
        "column": DIRTY_COL,
        "detector_id": ENGINE,
        "match_rate": 1.0,
        "severity": ENGINE,
        "configured_strategy": f"x/{ENGINE}",
        "sample_match_count": 3,
        "source_identity_rate": ENGINE,
        "source_compared": ENGINE,
        "message": f"leak {ENGINE} {CELL} {TABLE}",
        ENGINE: ENGINE,
    }
    return {
        "schema_version": ENGINE,
        "generated_at": ENGINE,
        "residual_pii": [finding, {**finding, "severity": "fail", "column": "email"}],
        "fk_preservation": [
            {
                "parent_table": TABLE,
                "parent_column": DIRTY_COL,
                "child_table": f"child_{TABLE}",
                "child_column": "id",
                "severity": "fail",
                "orphan_count": 2,
                "total_child_rows": 4,
                "orphan_rate": 0.5,
                "namespace": f"ns:{ENGINE}",
                "message": ENGINE,
            }
        ],
        "policy_validation": [
            {"table": TABLE, "column": "n", "strategy": f"<{ENGINE}>", "severity": "info",
             "source_distinct": ENGINE, "output_distinct": ENGINE, "bytes_identical": ENGINE,
             "message": ENGINE}
        ],
        "pass_count": 1,
        "warning_count": 0,
        "fail_count": 2,
        "error_count": 0,
        "pass_failed_with": f"{ENGINE}: {CELL}",
        ENGINE: {"nested": ENGINE},
    }  # fmt: skip


def _poisoned_quality(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {
        "schema_version": "quality-report/v1",
        "generated_at": ENGINE,
        "grade": ENGINE,
        "overall_score": 0.4,
        "sampled": ENGINE,
        "sample_size": ENGINE,
        "source": {"row_count": 10, "fingerprint": ENGINE},
        "output": {"row_count": 10, "fingerprint": ENGINE},
        "diagnostic": {"passed": False, "checks": [{"check": ENGINE, "missing_columns": [CELL]}]},
        "marginal": {
            "score": 0.5,
            "columns": [
                {"column": DIRTY_COL, "similarity": 0.5, "method": f"unknown_kind:{ENGINE}",
                 "comparable": ENGINE},
                {"column": "email", "similarity": ENGINE, "method": ENGINE},
            ],
        },
        "pairwise": {"joints": [{"columns": [DIRTY_COL, "n"], "similarity": 2.0, "method": "tvd",
                                 "comparable": ENGINE}]},
        "shape_fidelity": {
            "overall_shape_score": ENGINE,
            "marginal": {"columns": [
                {"column": DIRTY_COL, "shape_similarity": ENGINE, "method": ENGINE},
                {"column": "email", "shape_similarity": 0.5, "method": f"x/{ENGINE}"},
            ]},
            "pairwise": {"joints": [
                {"columns": [DIRTY_COL, "n"], "shape_similarity": ENGINE, "method": ENGINE},
            ]},
        },
        "warnings": [
            {"source": ENGINE, "code": ENGINE, "column": DIRTY_COL, "detail": {"v": CELL},
             "kind": ENGINE, "severity": ENGINE, "threshold": ENGINE, "metric": ENGINE},
        ],
        "omissions": [{"kind": "joint", "name": f"{DIRTY_COL}+n", "reason": ENGINE,
                       "method": ENGINE}],
        ENGINE: ENGINE,
    }  # fmt: skip


def _poisoned_policy(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {
        "schema_version": "quality-policy/v1",
        "verdict": "fail",
        "mode": "fail",
        "violations": [
            {"check": ENGINE, "severity": "fail", "expected": 0.9, "actual": 0.4,
             "detail": f"{ENGINE} {CELL}", "column": DIRTY_COL}
        ],
    }  # fmt: skip


from decoy_engine import profile_columns as _real_profile_columns  # noqa: E402


def _poisoned_profile(df: Any, **_k: Any) -> Any:
    real = _real_profile_columns(df, source_label=f"{PATH}.csv")
    data = real.to_dict()
    data["source_label"] = f"/home/{PATH}/{TABLE}.csv"
    data["quasi_identifier_groups"] = [[DIRTY_COL, "n"]]
    data["fields"].append(
        {
            "name": DIRTY_COL,
            "inferred_type": ENGINE,
            "null_rate": ENGINE,
            "distinct_count": -1,
            "pii_score": 0.9,
            "detector_matches": [{"detector_id": ENGINE, "sample_misses": [CELL]}],
            "top_values": [{"value": CELL}],
            "sentinels": [CELL],
        }
    )

    class _P:
        def to_dict(self) -> dict[str, Any]:
            return data

    return _P()


_DynExc = type(f"Exc_{EXC}_{CELL}", (Exception,), {})
BOOMS = {
    "runtime_error": lambda: RuntimeError(f"row {CELL} at /home/{PATH} table {TABLE} {EXC}"),
    "system_exit_text": lambda: SystemExit(f"SYSEXIT {CELL} {EXC}"),
    "dynamic_class": lambda: _DynExc(f"{CELL}"),
}
BOOM_TYPES = {
    "runtime_error": "RuntimeError",
    "system_exit_text": "SystemExit",
    "dynamic_class": "Exception",
}


def _boom_with(kind: str) -> Any:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise BOOMS[kind]()

    boom.__name__ = f"boom_{kind}"
    return boom


def _assert_error_type(result: Any, mode: str, kind: str) -> None:
    if mode == "json":
        assert _json.loads(result.stdout)["error_type"] == BOOM_TYPES[kind]


# ---------------------------------------------------------------------------
# 1. Containment.
# ---------------------------------------------------------------------------


def test_containment_restores_state_when_nested() -> None:
    before = _snapshot()
    with bd._contain_process() as outer:
        assert logging.root.manager.disable == sys.maxsize
        assert sys.stdout is not before[4]
        with bd._contain_process() as inner:
            assert inner.out is outer.out is before[4]
        assert logging.root.manager.disable == sys.maxsize
    assert _snapshot() == before


def test_containment_restores_state_under_overlapping_threads() -> None:
    before = _snapshot()
    entered = threading.Barrier(2)
    a_done = threading.Event()
    errors: list[BaseException] = []

    def a() -> None:
        try:
            with bd._contain_process():
                entered.wait()
            a_done.set()  # A leaves first: non-LIFO
        except BaseException as exc:
            errors.append(exc)

    def b() -> None:
        try:
            with bd._contain_process():
                entered.wait()
                a_done.wait(5)
                assert logging.root.manager.disable == sys.maxsize, "A's exit restored too early"
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=a), threading.Thread(target=b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    assert _snapshot() == before


def test_no_stray_output_reaches_the_real_streams(capfd: Any) -> None:
    with bd._contain_process():
        print(f"PRINT {CELL}")
        sys.stderr.write(f"STDERR {CELL}\n")
        warnings.warn(f"W {CELL}", UserWarning, stacklevel=1)
        logging.getLogger("decoy_engine").log(60, f"L {CELL}")
        logging.getLogger().critical(f"C {CELL}")
    out, err = capfd.readouterr()
    assert CELL not in out + err


# ---------------------------------------------------------------------------
# 2. Write exclusivity: non-vacuity, then the real commands.
# ---------------------------------------------------------------------------


def _compiled_as(filename: str, body: str) -> Any:
    namespace: dict[str, Any] = {"os": os}
    exec(compile(body, filename, "exec"), namespace)
    return namespace["evil"]


@pytest.mark.parametrize(
    ("origin", "body"),
    [
        (
            decoy_engine.__file__,
            "def evil(path):\n    with open(path, 'w') as fh:\n        fh.write('x')\n",
        ),
        (decoy_engine.__file__, "def evil(path):\n    os.write(2, b'x')\n"),
        (str(Path(CLI_SRC) / "pre_scan.py"), "def evil(path):\n    path.write_text('x')\n"),
        (
            str(Path(CLI_SRC) / "post_scan.py"),
            "def evil(path):\n    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)\n"
            "    os.write(fd, b'x')\n    os.close(fd)\n",
        ),
        (str(Path(CLI_SRC) / "_projections.py"), "def evil(path):\n    open(path, 'a').close()\n"),
    ],
)
def test_write_audit_catches_seeded_writes(tmp_path: Path, origin: str, body: str) -> None:
    evil = _compiled_as(origin, body)
    _AUDIT["on"] = True
    try:
        evil(tmp_path / "x.txt")
    finally:
        _AUDIT["on"] = False
    assert _AUDIT["violations"], "the write audit did not see a seeded write"
    _AUDIT["violations"] = []


def test_write_audit_catches_a_command_module_write_during_a_real_invocation(
    source: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import pre_scan

    stray = work / "stray.txt"
    evil = _compiled_as(
        pre_scan.__file__,
        "def evil(*a, **k):\n    open(STRAY, 'w').close()\n    return REAL(*a, **k)\n",
    )
    evil.__globals__.update(STRAY=stray, REAL=pre_scan._load_data)
    monkeypatch.setattr(pre_scan, "_load_data", evil)
    _AUDIT["on"] = True
    try:
        runner.invoke(app, ["pre-scan", str(source)])
    finally:
        _AUDIT["on"] = False
    assert _AUDIT["violations"], "a command-module write went unnoticed"
    _AUDIT["violations"] = []


# ---------------------------------------------------------------------------
# 3. Canaries.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_pre_scan_success_and_saved_scan(source, work, monkeypatch, caplog, spies, mode) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(decoy_engine, "profile_columns", _noisy(_poisoned_profile))
    saved = work / f"scan_{REPORT}.json"
    _CALLS.clear()
    for flags in ([], ["--show-fields"], ["--output", str(saved)]):
        r = _invoke(["pre-scan", str(source), *flags, *MODES[mode]])
        assert r.exit_code == 0, r.output
        files = (saved,) if "--output" in flags else ()
        _scan(r, caplog, *files, raw_artifacts=files, mode=mode, ok=True, expect_debug=True)
    assert len(_CALLS) == 3, "the noisy engine stand-in did not run"
    if mode == "text":
        r = _invoke(["pre-scan", str(source), "--output", "-"])
        assert r.exit_code == 0
        _scan(r, caplog, mode=mode, ok=True, streamed=True)
    for argv, ok in (
        (["fields", str(saved)], True),
        (["show", str(saved), "email"], True),
        (["show", str(saved), "field-3"], True),
        (["show", str(saved), f"x{DIRTY_COL}"], False),
        (["diff", str(saved), str(saved)], True),
        (["fields", str(work / f"missing_{PATH}.json")], False),
    ):
        r = _invoke(["pre-scan", *argv, *MODES[mode]])
        assert (r.exit_code == 0) is ok, (argv, r.output)
        _scan(r, caplog, mode=mode, ok=ok)


def test_saved_scan_is_owner_only_even_over_an_existing_world_readable_file(source, work) -> None:
    saved = work / f"scan_{REPORT}.json"
    saved.write_text("{}")
    saved.chmod(0o644)
    old = os.umask(0o000)
    try:
        r = _invoke(["pre-scan", str(source), "--output", str(saved)])
    finally:
        os.umask(old)
    assert r.exit_code == 0, r.output
    assert (saved.stat().st_mode & 0o777) == 0o600
    assert _json.loads(saved.read_text())["source_label"] == "source"


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_pre_scan_layout_values_never_echo(source, work, caplog, mode) -> None:
    caplog.set_level(logging.DEBUG)
    layouts = {
        "neg_start": f"columns:\n  - {{name: a, start: -{LAYOUT_NUM}, width: 3}}\n",
        "bad_width": f"columns:\n  - {{name: a, start: 0, width: {LAYOUT_TXT}}}\n",
        "neg_width": f"columns:\n  - {{name: a, start: 0, width: -{LAYOUT_NUM}}}\n",
        "not_list": f"columns: {LAYOUT_TXT}\n",
        "entry": f"columns:\n  - {LAYOUT_TXT}\n",
        "garbage": f"{{[{LAYOUT_TXT}: {LAYOUT_NUM}",
    }
    for label, text in layouts.items():
        lay = work / f"layout_{label}_{PATH}.yaml"
        lay.write_text(text)
        r = _invoke(
            ["pre-scan", str(source), "--format", "fixed-width", "--layout", str(lay),
             *MODES[mode]],
        )  # fmt: skip
        assert r.exit_code != 0, label
        _scan(r, caplog, mode=mode, ok=False)
    if mode == "json":
        lay = work / f"layout_neg_start_{PATH}.yaml"
        r = _invoke(
            ["pre-scan", str(source), "--format", "fixed-width", "--layout", str(lay), "--json"]
        )
        payload = _json.loads(r.stdout)
        assert payload["reason"] == "layout_invalid"
        assert payload["location"] == {
            "kind": "layout", "index": 0, "key": "start", "rule": "start_negative"
        }  # fmt: skip


@pytest.mark.parametrize("kind", sorted(BOOMS))
@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_pre_scan_engine_exception_never_echoes(
    source, monkeypatch, caplog, spies, mode, kind
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(decoy_engine, "profile_columns", _noisy(_boom_with(kind)))
    r = _invoke(["pre-scan", str(source), *MODES[mode]])
    assert r.exit_code == 3, r.output
    _scan(r, caplog, mode=mode, ok=False, expect_debug=True)
    _assert_error_type(r, mode, kind)


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_post_scan_integrity_projection_only(
    source, masked, work, monkeypatch, caplog, spies, mode
):
    caplog.set_level(logging.DEBUG)
    import decoy_engine.verification as ver

    cfg = work / f"cfg_{PATH}.yaml"
    cfg.write_text(
        f"version: 2\nsources:\n  {TABLE}:\n    path: {work / f'other_{PATH}.csv'}\n"
        f"tables:\n  - name: {TABLE}\n    source: {TABLE}\n"
    )
    out = work / f"out_{REPORT}.json"
    # Real engine first (table name from config and from the masked file stem).
    for extra in ([], ["--config", str(cfg)]):
        r = _invoke(
            ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(out),
             *extra, *MODES[mode]],
        )  # fmt: skip
        assert r.exit_code in (0, 1, 4), r.output
        _scan(r, caplog, out, mode=mode, ok=r.exit_code in (0, 4))
    # Every engine field poisoned: success path still emits only the projection.
    monkeypatch.setattr(ver, "run_post_mask", _noisy(_poisoned_integrity))
    r = _invoke(
        ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(out),
         *MODES[mode]],
    )  # fmt: skip
    assert r.exit_code == 4, r.output
    _scan(r, caplog, out, mode=mode, ok=True, expect_debug=True)
    written = _json.loads(out.read_text())
    assert written["schema_version"] == "integrity-report/v1"
    assert {f["table"] for f in written["residual_pii"]} == {"table-1"}
    assert written["pass_failed_with"] == "Exception"
    assert written["policy_validation"][0]["source_distinct"] is None
    assert written["residual_pii"][0]["source_compared"] is False
    # Error paths.
    for kind in sorted(BOOMS):
        monkeypatch.setattr(ver, "run_post_mask", _noisy(_boom_with(kind)))
        r = _invoke(["post-scan", "integrity", str(masked), "--source", str(source), *MODES[mode]])
        assert r.exit_code == 3, (kind, r.output)
        _scan(r, caplog, mode=mode, ok=False, expect_debug=True)
        _assert_error_type(r, mode, kind)


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_post_scan_fidelity_projection_only(source, masked, work, monkeypatch, caplog, spies, mode):
    caplog.set_level(logging.DEBUG)
    import decoy_engine.quality as q

    rep = work / f"fid_{REPORT}.json"
    base = ["post-scan", "fidelity", str(source), str(masked), "--report-out", str(rep)]
    r = _invoke([*base, *MODES[mode]])
    assert r.exit_code in (0, 4), r.output
    _scan(r, caplog, rep, mode=mode, ok=True)
    monkeypatch.setattr(q, "compute_quality_report", _noisy(_poisoned_quality))
    monkeypatch.setattr(q, "apply_quality_policy", _poisoned_policy)
    r = _invoke([*base, "--joint", "email,n", *MODES[mode]])
    assert r.exit_code == 4, r.output
    _scan(r, caplog, rep, mode=mode, ok=True, expect_debug=True)
    written = _json.loads(rep.read_text())
    assert written["schema_version"] == "fidelity-report/v1"
    assert written["grade"] is None
    assert written["sampled"] is False and written["sample_size"] is None
    assert written["warnings"][0]["threshold"] is None
    assert written["omissions"][0]["method"] == "unrecognized"
    for kind in sorted(BOOMS):
        monkeypatch.setattr(q, "compute_quality_report", _noisy(_boom_with(kind)))
        r = _invoke([*base, *MODES[mode]])
        assert r.exit_code == 3, (kind, r.output)
        _scan(r, caplog, mode=mode, ok=False, expect_debug=True)
        _assert_error_type(r, mode, kind)


@pytest.mark.parametrize("command", ["integrity", "fidelity"])
@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_config_validation_warnings_are_contained(
    source, masked, work, monkeypatch, caplog, spies, command, mode
) -> None:
    """A warning raised inside `PipelineConfig.model_validate` -- which runs before any
    engine call -- is recorded by the boundary like every other warning."""
    caplog.set_level(logging.DEBUG)
    from decoy_engine import PipelineConfig

    original = PipelineConfig.model_validate.__func__  # type: ignore[attr-defined]
    seen: list[int] = []

    def noisy_validate(cls: Any, obj: Any, *a: Any, **k: Any) -> Any:
        seen.append(1)
        warnings.warn(f"CFG_WARN {WARN} {CELL}", UserWarning, stacklevel=1)
        logging.getLogger("decoy_engine").log(60, f"CFG_LOG {CELL}")
        return original(cls, obj, *a, **k)

    monkeypatch.setattr(PipelineConfig, "model_validate", classmethod(noisy_validate))
    cfg = work / f"cfg_{PATH}.yaml"
    cfg.write_text(f"version: 2\ntables:\n  - name: {TABLE}\n    source: {TABLE}\n")
    argv = {
        "integrity": ["post-scan", "integrity", str(masked), "--source", str(source)],
        "fidelity": ["post-scan", "fidelity", str(source), str(masked)],
    }[command]
    r = _invoke([*argv, "--config", str(cfg), *MODES[mode]])
    assert seen, "model_validate was not exercised"
    _scan(r, caplog, mode=mode, ok=r.exit_code in (0, 4), expect_debug=True)


@pytest.mark.parametrize("command", ["pre-scan", "integrity", "fidelity"])
def test_debug_log_path_is_rejected_value_free(source, masked, work, caplog, command) -> None:
    """There is no `--debug-log`: the flag is refused without echoing its path or writing it."""
    log = work / f"debug_{DEBUG}.log"
    argv = {
        "pre-scan": ["pre-scan", str(source)],
        "integrity": ["post-scan", "integrity", str(masked), "--source", str(source)],
        "fidelity": ["post-scan", "fidelity", str(source), str(masked)],
    }[command]
    for mode, flags in MODES.items():
        r = _invoke([*argv, "--debug-log", str(log), *flags])
        assert r.exit_code != 0
        _scan(r, caplog, mode=mode, ok=False)
    assert not log.exists()


def test_parser_and_group_errors_are_value_free(source, work, caplog) -> None:
    """Group-level parse errors run inside the boundary too: no echoed option or path."""
    for mode, flags in MODES.items():
        for argv in (
            ["pre-scan", f"--{PATH}"],
            ["post-scan", f"--{PATH}"],
            ["post-scan", "integrity", str(work / f"no_{PATH}.csv"), "--source", str(source)],
            ["pre-scan", "show", str(work / f"no_{PATH}.json")],
        ):
            r = _invoke([*argv, *flags])
            assert r.exit_code != 0, argv
            _scan(r, caplog, mode=mode, ok=False)


def test_help_still_reaches_stdout() -> None:
    for argv in (["pre-scan", "--help"], ["post-scan", "fidelity", "--help"], ["pre-scan"]):
        r = _invoke(argv)
        assert "Usage" in r.stdout, argv


def test_unwritable_report_paths_never_echo(source, masked, work, caplog) -> None:
    bad = work / f"no_dir_{REPORT}" / f"r_{PATH}.json"
    for argv in (
        ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(bad)],
        ["post-scan", "fidelity", str(source), str(masked), "--report-out", str(bad)],
        ["pre-scan", str(source), "--output", str(bad)],
    ):
        for mode, flags in MODES.items():
            r = _invoke([*argv, *flags])
            assert r.exit_code == 3, r.output
            _scan(r, caplog, mode=mode, ok=False)
