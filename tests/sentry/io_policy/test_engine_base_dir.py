"""G-BASE-DIR: every CLI call of an engine entry that reads a path from the YAML passes `base_dir=`.

A relative path in the YAML is read from the config file's folder. The engine applies that rule
only when the caller hands it the folder, so a call without `base_dir=` reads a relative
`snapshot_file`, `column_names_file` or `quarantine.output_path` from the working directory and
`validate` and `run` can disagree on one YAML. The engine keeps `base_dir` optional (the platform
and library callers pass none), so this walk is the guard on the CLI side.

Walks every module under `src/decoy/` for a call of a watched entry in any spelling the shared
scanner resolves (direct import, module alias, `from` alias, an imported submodule attribute) and
fails on one that lacks a `base_dir=` keyword. A positional `base_dir` does not count, so a
positional argument can never hide a missing keyword. Named limits are the shared scanner's: a
call through a runtime-bound name, an alias by assignment, `from x import *`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import call_contexts

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"

WATCHED = frozenset(
    {
        "run_pipeline",
        "run_pipeline_isolated",
        "compile_plan",
        "run_config_only_checks",
        "validate_plan",
        "compile_pinned_plan",
        "compile_pinned_plan_with_generation",
        "estimate_job_capacity",
        "estimate_job",
        "capture_physical_plan_inputs",
    }
)


# Entries that open the config's declared source files themselves. Their config argument must
# come from `resolved_source_config(...)`, or a relative source reads from the working directory.
SOURCE_READERS = frozenset({"run_pipeline", "profile_source"})


def _source_readers(package: str, name: str) -> bool:
    return package.split(".")[0] == "decoy_engine" and name in SOURCE_READERS


def raw_config_calls(source: str) -> list[tuple[int, str]]:
    """Return (line, scope) for each source-reading entry whose config is not resolved."""
    bad = []
    for call, scope, _names in call_contexts(
        source, qualified_match=_source_readers, with_calls=frozenset()
    ):
        first = call.args[0] if call.args else None
        ok = (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Name)
            and first.func.id == "resolved_source_config"
        )
        if not ok:
            bad.append((call.lineno, scope))
    return bad


def _watched(package: str, name: str) -> bool:
    return package.split(".")[0] == "decoy_engine" and name in WATCHED


def entry_calls(source: str) -> list[tuple[int, str, bool]]:
    """Return (line, qualified scope, passes `base_dir=`) for each watched engine call."""
    return [
        (call.lineno, scope, any(kw.arg == "base_dir" for kw in call.keywords))
        for call, scope, _names in call_contexts(
            source, qualified_match=_watched, with_calls=frozenset()
        )
    ]


def _walk(root: Path) -> list[tuple[str, int, str, bool]]:
    found: list[tuple[str, int, str, bool]] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        for line, scope, ok in entry_calls(path.read_text(encoding="utf-8")):
            found.append((rel, line, scope, ok))
    return found


def test_every_engine_entry_call_passes_base_dir() -> None:
    missing = [(f, ln, sc) for f, ln, sc, ok in _walk(SRC) if not ok]
    assert not missing, f"engine entry called without base_dir=: {missing}"


def test_the_walk_sees_the_known_call_sites() -> None:
    # Non-vacuity: the nine sites the plan lists, plus tokenize and the preflight pair.
    files = {f for f, _ln, _sc, _ok in _walk(SRC)}
    assert {
        "api.py",
        "cli/run/_execute.py",
        "cli/tokenize.py",
        "cli/demo.py",
        "cli/compile_explain.py",
        "cli/preflight.py",
        "cli/gate/_layers.py",
    } <= files


SEEDED = {
    "direct import": (
        "from decoy_engine import compile_plan\n"
        "def f(raw, p):\n    return compile_plan(raw, p, decoy_engine_version='1')\n"
    ),
    "module alias": (
        "import decoy_engine as de\ndef f(raw):\n    return de.run_config_only_checks(raw)\n"
    ),
    "from alias": (
        "from decoy_engine import run_pipeline as rp\ndef f(c, s):\n    return rp(c, s, engine_version='1')\n"
    ),
    "submodule attribute": (
        "import decoy_engine.plan\n"
        "def f(raw, p):\n    return decoy_engine.plan.compile_plan(raw, p, decoy_engine_version='1')\n"
    ),
    "positional base_dir": (
        "from decoy_engine.execution import estimate_job_capacity\n"
        "def f(d, p):\n    return estimate_job_capacity(d, p)\n"
    ),
}


@pytest.mark.parametrize("name", sorted(SEEDED))
def test_seeded_bypass_is_seen(name: str) -> None:
    calls = entry_calls(SEEDED[name])
    assert len(calls) == 1
    assert calls[0][2] is False


def test_a_call_with_base_dir_passes() -> None:
    src = (
        "from decoy_engine import compile_plan\n"
        "def f(raw, p, d):\n"
        "    return compile_plan(raw, p, decoy_engine_version='1', base_dir=d)\n"
    )
    assert [ok for *_x, ok in entry_calls(src)] == [True]


def test_an_unwatched_package_is_ignored() -> None:
    src = "from other import compile_plan\ndef f(raw):\n    return compile_plan(raw)\n"
    assert entry_calls(src) == []


def test_source_readers_get_a_resolved_config() -> None:
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        bad += [(rel, ln, sc) for ln, sc in raw_config_calls(path.read_text(encoding="utf-8"))]
    assert not bad, f"raw config handed to an engine source reader: {bad}"


def test_a_raw_config_to_a_source_reader_is_seen() -> None:
    raw = (
        "from decoy_engine.profile import profile_source\ndef f(c):\n    return profile_source(c)\n"
    )
    ok = (
        "from decoy_engine.profile import profile_source\n"
        "def f(c, d):\n    return profile_source(resolved_source_config(c, d))\n"
    )
    assert len(raw_config_calls(raw)) == 1
    assert raw_config_calls(ok) == []
