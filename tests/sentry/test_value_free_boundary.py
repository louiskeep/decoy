"""Build-failing sentry: pre-scan and post-scan reach a surface only through the boundary.

Two halves, both required:

1. Structure (AST). `pre_scan.py` and `post_scan.py` cannot print, serialize, write
   files or touch a console themselves; an exception they catch can only be handed
   to the boundary as `exc=`; every registered command is wrapped by
   `_value_free.guarded`; a `Projection` cannot be built outside the projections
   module. A new call site that bypasses the boundary fails here, not in review.

2. Canaries. Distinct tokens are seeded into a source path, a table name, invalid
   layout values, every free-text and identifier field of the engine reports, engine
   exception messages, engine warnings and log records, and the `--report-out`,
   `--output` and `--debug-log` paths. Every surface -- stdout, stderr, the JSON
   envelope, the written report, captured logs, `--verbose` -- is scanned across
   pre-scan (and fields/show/diff), post-scan integrity and post-scan fidelity, on
   success and error paths.

Policy the canaries respect by design: a short clean-charset COLUMN name is schema
and is printed (same rule as the platform's `fidelity-report/v1`), so column
canaries here use characters a column name policy must reject. Table names are
always opaque, so the table canary is clean-charset on purpose. The pre-scan
`--output FILE` saved scan is the one explicit raw artifact: it may hold cell
values, but never a path, exception text or layout value.
"""

from __future__ import annotations

import ast
import json as _json
import logging
import warnings
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import _value_free as vf

runner = CliRunner()
SRC = Path(__file__).resolve().parents[2] / "src" / "decoy" / "cli"
COMMAND_MODULES = ("pre_scan.py", "post_scan.py")

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
# 1. Structure
# ---------------------------------------------------------------------------

BANNED_NAMES = {
    "print",
    "emit_json",
    "setup_output",
    "render_card",
    "make_table",
    "sanitize_yaml_error",
    "OutputState",
    "Projection",
    "mint",
    "repr",
}
BANNED_ATTRS = {
    "console",
    "err_console",
    "stdout",
    "stderr",
    "write_text",
    "write_bytes",
    "echo",
    "dumps",
    "dump",
    "mint",
    "write_saved_scan_raw",
}


def _tree(name: str) -> ast.Module:
    return ast.parse((SRC / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", COMMAND_MODULES)
def test_command_modules_have_no_direct_output_path(module: str) -> None:
    hits = []
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            hits.append(f"{node.lineno}: name {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
            hits.append(f"{node.lineno}: .{node.attr}")
        if isinstance(node, ast.alias) and node.name in BANNED_NAMES:
            hits.append(f"{node.lineno}: import {node.name}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            hits.append(f"{node.lineno}: open()")
    assert not hits, f"{module} bypasses the value-free boundary: {hits}"


@pytest.mark.parametrize("module", COMMAND_MODULES)
def test_caught_exceptions_only_reach_the_boundary_as_exc(module: str) -> None:
    """`str(exc)`, f"{exc}", exc.args, logging(exc) -- all impossible.

    Allowed: `exc=exc` to the boundary, `isinstance(exc, ...)` to pick a reason,
    `vf.yaml_location(exc)` (line/column ints only) and `exc.location` (a typed
    LayoutError location of closed codes).
    """
    tree = _tree(module)
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "exc" and isinstance(node.value, ast.Name):
            allowed.add(id(node.value))
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Name):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if fname in ("isinstance", "yaml_location"):
                allowed.add(id(node.args[0]))
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "location"
            and isinstance(node.value, ast.Name)
        ):
            allowed.add(id(node.value))
    bad = []
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        for stmt in handler.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and node.id == handler.name and id(node) not in allowed:
                    bad.append(f"{node.lineno}: {handler.name}")
    assert not bad, f"{module} uses a caught exception outside `exc=`: {bad}"


def test_every_command_is_guarded() -> None:
    from decoy.cli.post_scan import post_scan_app
    from decoy.cli.pre_scan import pre_scan_app

    for typer_app in (pre_scan_app, post_scan_app):
        assert typer_app.registered_commands
        for cmd in typer_app.registered_commands:
            assert getattr(cmd.callback, "__value_free_guard__", None), cmd.name


def test_projection_cannot_be_forged_and_raw_dicts_cannot_be_emitted(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        vf.Projection("x/v1", {"a": 1})
    surface = vf.Surface("t", True, False, False)
    for call in (
        lambda: surface.emit({"raw": ENGINE}, status="ok"),  # type: ignore[arg-type]
        lambda: surface.stream({"raw": ENGINE}),  # type: ignore[arg-type]
        lambda: surface.write(tmp_path / "r.json", {"raw": ENGINE}),  # type: ignore[arg-type]
    ):
        with pytest.raises(TypeError):
            call()
    with pytest.raises(TypeError):
        vf.mint("x/v1", {"bad": object()})


def test_reasons_and_layout_errors_are_closed() -> None:
    with pytest.raises(KeyError):
        vf.REASONS[f"free text {ENGINE}"]
    with pytest.raises(ValueError):
        vf.LayoutError(f"{LAYOUT_TXT}")
    with pytest.raises(ValueError):
        vf.LayoutError("not_integer", index=0, key=LAYOUT_TXT)
    for reason in vf.REASONS.values():
        assert "{" not in reason.message and "{" not in (reason.hint or "")


def test_projections_never_read_engine_free_text() -> None:
    text = (SRC / "_projections.py").read_text(encoding="utf-8")
    for key in ('"message"', '"detail"', '"source_label"', '"sample_invalid"', '"samples"'):
        assert f".get({key})" not in text and f"[{key}]" not in text, key
    # Raw value containers may only be tested for presence, never read.
    assert text.count('"top_values"') == text.count('bool(field.get("top_values"))') == 1


# ---------------------------------------------------------------------------
# 2. Canaries
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


def _scan(result, caplog, *files: Path, raw_artifacts: tuple[Path, ...] = ()) -> None:
    """`raw_artifacts` (the pre-scan saved scan) may hold engine profile content and
    cell values; never a path, table label, exception, layout value or warning."""
    parts = [result.stdout or "", result.stderr or ""]
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        parts.append(f"UNCAUGHT {type(result.exception).__name__}: {result.exception}")
    parts.extend(r.getMessage() for r in caplog.records)
    text = "\n".join(parts)
    for canary in CANARIES:
        assert canary not in text, f"{canary} leaked to a stream/log:\n{text}"
    assert "Traceback" not in text
    for f in files:
        if not f.exists():
            continue
        body = f.read_text(encoding="utf-8", errors="replace")
        for canary in CANARIES:
            if canary in (CELL, ENGINE) and f in raw_artifacts:
                continue
            assert canary not in body, f"{canary} leaked into written file {f.name}"
    assert not (result.exception is not None and not isinstance(result.exception, SystemExit))


def _noisy(fn):
    """Engine stand-in that also emits a warning and log records carrying canaries."""

    def wrapper(*a: Any, **k: Any) -> Any:
        warnings.warn(f"engine says {WARN} {CELL}", UserWarning, stacklevel=1)
        logging.getLogger("decoy_engine.x").warning("engine log %s %s", WARN, TABLE)
        logging.getLogger().error("root log %s", WARN)
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
             "message": ENGINE}
        ],
        "pass_count": 1,
        "warning_count": 0,
        "fail_count": 2,
        "error_count": 0,
        "pass_failed_with": f"{ENGINE}: {CELL}",
        ENGINE: {"nested": ENGINE},
    }


def _poisoned_quality(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {
        "schema_version": "quality-report/v1",
        "generated_at": ENGINE,
        "grade": ENGINE,
        "overall_score": 0.4,
        "source": {"row_count": 10, "fingerprint": ENGINE},
        "output": {"row_count": 10, "fingerprint": ENGINE},
        "diagnostic": {"passed": False, "checks": [{"check": ENGINE, "missing_columns": [CELL]}]},
        "marginal": {
            "score": 0.5,
            "columns": [
                {"column": DIRTY_COL, "similarity": 0.5, "method": f"unknown_kind:{ENGINE}"},
                {"column": "email", "similarity": ENGINE, "method": ENGINE},
            ],
        },
        "pairwise": {"joints": [{"columns": [DIRTY_COL, "n"], "similarity": 2.0, "method": "tvd"}]},
        "warnings": [
            {"source": ENGINE, "code": ENGINE, "column": DIRTY_COL, "detail": {"v": CELL}},
        ],
        "omissions": [{"kind": "joint", "name": f"{DIRTY_COL}+n", "reason": ENGINE}],
        ENGINE: ENGINE,
    }


def _poisoned_policy(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {
        "schema_version": "quality-policy/v1",
        "verdict": "fail",
        "mode": "fail",
        "violations": [
            {"check": ENGINE, "severity": "fail", "expected": 0.9, "actual": 0.4,
             "detail": f"{ENGINE} {CELL}", "column": DIRTY_COL}
        ],
    }


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


def _boom(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError(f"row {CELL} at /home/{PATH} table {TABLE} {EXC}")


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_pre_scan_success_and_saved_scan(source, work, monkeypatch, caplog, mode) -> None:
    caplog.set_level(logging.DEBUG)
    import decoy_engine

    monkeypatch.setattr(decoy_engine, "profile_columns", _noisy(_poisoned_profile))
    saved = work / f"scan_{REPORT}.json"
    for flags in ([], ["--show-fields"], ["--output", str(saved)]):
        r = runner.invoke(app, ["pre-scan", str(source), *flags, *MODES[mode]])
        assert r.exit_code == 0, r.output
        _scan(r, caplog, saved, raw_artifacts=(saved,))
    if mode == "text":
        r = runner.invoke(app, ["pre-scan", str(source), "--output", "-"])
        assert r.exit_code == 0
        _scan(r, caplog)
    assert saved.exists()
    for argv in (
        ["fields", str(saved)],
        ["show", str(saved), "email"],
        ["show", str(saved), "field-3"],
        ["show", str(saved), f"x{DIRTY_COL}"],
        ["diff", str(saved), str(saved)],
        ["fields", str(work / f"missing_{PATH}.json")],
    ):
        r = runner.invoke(app, ["pre-scan", *argv, *MODES[mode]])
        _scan(r, caplog)


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
        r = runner.invoke(
            app,
            ["pre-scan", str(source), "--format", "fixed-width", "--layout", str(lay),
             *MODES[mode]],
        )
        assert r.exit_code != 0, label
        _scan(r, caplog)
    if mode == "json":
        lay = work / f"layout_neg_start_{PATH}.yaml"
        r = runner.invoke(
            app, ["pre-scan", str(source), "--format", "fixed-width", "--layout", str(lay), "--json"]
        )
        payload = _json.loads(r.stdout)
        assert payload["reason"] == "layout_invalid"
        assert payload["location"] == {
            "kind": "layout", "index": 0, "key": "start", "rule": "start_negative"
        }


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_pre_scan_engine_exception_never_echoes(source, monkeypatch, caplog, mode) -> None:
    caplog.set_level(logging.DEBUG)
    import decoy_engine

    monkeypatch.setattr(decoy_engine, "profile_columns", _noisy(_boom))
    r = runner.invoke(app, ["pre-scan", str(source), *MODES[mode]])
    assert r.exit_code == 3
    _scan(r, caplog)


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_post_scan_integrity_projection_only(source, masked, work, monkeypatch, caplog, mode):
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
        r = runner.invoke(
            app,
            ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(out),
             *extra, *MODES[mode]],
        )
        assert r.exit_code in (0, 1, 4), r.output
        _scan(r, caplog, out)
    # Every engine field poisoned: success path still emits only the projection.
    monkeypatch.setattr(ver, "run_post_mask", _noisy(_poisoned_integrity))
    r = runner.invoke(
        app,
        ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(out),
         *MODES[mode]],
    )
    assert r.exit_code == 4, r.output
    _scan(r, caplog, out)
    written = _json.loads(out.read_text())
    assert written["schema_version"] == "integrity-report/v1"
    assert {f["table"] for f in written["residual_pii"]} == {"table-1"}
    # Error path.
    monkeypatch.setattr(ver, "run_post_mask", _noisy(_boom))
    r = runner.invoke(
        app, ["post-scan", "integrity", str(masked), "--source", str(source), *MODES[mode]]
    )
    assert r.exit_code == 3
    _scan(r, caplog)


@pytest.mark.parametrize("mode", MODES, ids=list(MODES))
def test_post_scan_fidelity_projection_only(source, masked, work, monkeypatch, caplog, mode):
    caplog.set_level(logging.DEBUG)
    import decoy_engine.quality as q

    rep = work / f"fid_{REPORT}.json"
    base = ["post-scan", "fidelity", str(source), str(masked), "--report-out", str(rep)]
    r = runner.invoke(app, [*base, *MODES[mode]])
    assert r.exit_code in (0, 4), r.output
    _scan(r, caplog, rep)
    monkeypatch.setattr(q, "compute_quality_report", _noisy(_poisoned_quality))
    monkeypatch.setattr(q, "apply_quality_policy", _poisoned_policy)
    r = runner.invoke(app, [*base, "--joint", "email,n", *MODES[mode]])
    assert r.exit_code == 4, r.output
    _scan(r, caplog, rep)
    written = _json.loads(rep.read_text())
    assert written["schema_version"] == "fidelity-report/v1"
    assert written["grade"] is None
    monkeypatch.setattr(q, "compute_quality_report", _noisy(_boom))
    r = runner.invoke(app, [*base, *MODES[mode]])
    assert r.exit_code == 3
    _scan(r, caplog)


@pytest.mark.parametrize("command", ["pre-scan", "integrity", "fidelity"])
def test_debug_log_path_is_rejected_value_free(source, masked, work, caplog, command) -> None:
    """There is no `--debug-log`: the flag is refused without echoing its path or writing it."""
    log = work / f"debug_{DEBUG}.log"
    argv = {
        "pre-scan": ["pre-scan", str(source)],
        "integrity": ["post-scan", "integrity", str(masked), "--source", str(source)],
        "fidelity": ["post-scan", "fidelity", str(source), str(masked)],
    }[command]
    for mode in MODES.values():
        r = runner.invoke(app, [*argv, "--debug-log", str(log), *mode])
        assert r.exit_code != 0
        _scan(r, caplog)
    assert not log.exists()


def test_unwritable_report_paths_never_echo(source, masked, work, caplog) -> None:
    bad = work / f"no_dir_{REPORT}" / f"r_{PATH}.json"
    for argv in (
        ["post-scan", "integrity", str(masked), "--source", str(source), "--output", str(bad)],
        ["post-scan", "fidelity", str(source), str(masked), "--report-out", str(bad)],
        ["pre-scan", str(source), "--output", str(bad)],
    ):
        for mode in MODES.values():
            r = runner.invoke(app, [*argv, *mode])
            assert r.exit_code == 3, r.output
            _scan(r, caplog)
