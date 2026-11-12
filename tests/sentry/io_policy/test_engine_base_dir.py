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

The same walk also guards the quarantine path. A `run_pipeline` call that omits `quarantine_path=`,
or hides it in `**kwargs`, can write a quarantine file at a place the run layout never saw. Each call
passes it as a direct `place_quarantine(...)` call; the one preview call, which has no layout and
writes nothing, passes the literal `None`.
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


# The one call that has no layout: the `--rows` preview. `refuse_preview` rejects an enabled
# quarantine before it, so it passes the literal `None`.
QUARANTINE_NONE_SITES = frozenset({("cli/run/_execute.py", "execute_preview")})


def _is_engine_run_pipeline(package: str, name: str) -> bool:
    return package.split(".")[0] == "decoy_engine" and name == "run_pipeline"


def quarantine_issues(source: str, rel: str) -> list[tuple[int, str, str]]:
    """Return (line, scope, problem) for each `run_pipeline` call whose `quarantine_path=` is wrong."""
    issues = []
    for call, scope, _names in call_contexts(
        source, qualified_match=_is_engine_run_pipeline, with_calls=frozenset()
    ):
        values = [kw.value for kw in call.keywords if kw.arg == "quarantine_path"]
        if not values:
            issues.append((call.lineno, scope, "no quarantine_path= keyword"))
            continue
        value = values[0]
        if (rel, scope) in QUARANTINE_NONE_SITES:
            if not (isinstance(value, ast.Constant) and value.value is None):
                issues.append((call.lineno, scope, "the preview call must pass literal None"))
        elif not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "place_quarantine"
        ):
            issues.append((call.lineno, scope, "not a direct place_quarantine(...) call"))
    return issues


def test_every_run_pipeline_call_passes_an_explicit_quarantine_path() -> None:
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        bad += [(rel, *i) for i in quarantine_issues(path.read_text(encoding="utf-8"), rel)]
    assert not bad, f"run_pipeline quarantine_path= is not explicit: {bad}"


def test_the_quarantine_rule_covers_the_four_calls() -> None:
    sites = set()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for _call, scope, _names in call_contexts(
            path.read_text(encoding="utf-8"),
            qualified_match=_is_engine_run_pipeline,
            with_calls=frozenset(),
        ):
            sites.add((rel, scope))
    assert sites == {
        ("api.py", "mask"),
        ("cli/run/_execute.py", "execute"),
        ("cli/run/_execute.py", "execute_preview"),
        ("cli/tokenize.py", "tokenize"),
    }
    assert QUARANTINE_NONE_SITES <= sites


_QP = "from decoy_engine import run_pipeline\ndef {scope}(layout, c, s, kw, q):\n    return run_pipeline(c, s, {args})\n"
_PREVIEW = ("cli/run/_execute.py", "execute_preview")
_WRITER = ("cli/tokenize.py", "tokenize")

QUARANTINE_CASES = {
    "direct call": (_WRITER, "quarantine_path=layout.place_quarantine(c)", True),
    "kwargs only": (_WRITER, "**kw", False),
    "no keyword": (_WRITER, "engine_version='1'", False),
    "forwarded local": (_WRITER, "quarantine_path=q", False),
    "none in a writing route": (_WRITER, "quarantine_path=None", False),
    "literal none at the preview": (_PREVIEW, "quarantine_path=None", True),
    "placed value at the preview": (_PREVIEW, "quarantine_path=layout.place_quarantine(c)", False),
    "kwargs only at the preview": (_PREVIEW, "**kw", False),
    "none in another scope of the preview file": (
        ("cli/run/_execute.py", "execute"),
        "quarantine_path=None",
        False,
    ),
}


@pytest.mark.parametrize("name", sorted(QUARANTINE_CASES))
def test_the_quarantine_rule_accepts_and_rejects_each_spelling(name: str) -> None:
    (rel, scope), args, ok = QUARANTINE_CASES[name]
    src = _QP.format(scope=scope, args=args)
    assert (quarantine_issues(src, rel) == []) is ok


def test_the_quarantine_rule_sees_an_aliased_run_pipeline() -> None:
    src = (
        "import decoy_engine as de\n"
        "def tokenize(c, s):\n    return de.run_pipeline(c, s, engine_version='1')\n"
    )
    assert len(quarantine_issues(src, "cli/tokenize.py")) == 1
