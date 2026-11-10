"""G-ONE-PROFILE-WRITER: a profile reaches a file only through the engine's `profile_document`.

`ColumnProfile.to_dict()` keeps every cell value the profiler saw (top values, modes, ranges).
`decoy_engine.profile_document` passes the same dict through the engine redactor, so a CLI route
that serializes a profile must call it instead. This walks every module under `src/decoy` and
flags `.to_dict()` on a name bound from `profile_columns(...)` in the same function, or straight
on the call (`profile_columns(df).to_dict()`).

Named limits: a profile passed through a parameter, an attribute, a container or a second
assignment is not followed, and neither is a call through a runtime-bound name. The realistic
bypass is the one this repo had: `profile = profile_columns(...)` then `profile.to_dict()`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.sentry.io_policy._calls import sites

_SRC = Path(__file__).resolve().parents[3] / "src" / "decoy"
_PRODUCER = "profile_columns"


def _is_producer(call: ast.AST, name: str | None) -> bool:
    if not isinstance(call, ast.Call):
        return False
    if name is not None:
        return name.rpartition(".")[2] == _PRODUCER
    return isinstance(call.func, ast.Name) and call.func.id == _PRODUCER


def offenders(source: str) -> list[int]:
    """Line numbers where `source` serializes a raw profile with `.to_dict()`."""
    found = sites(ast.parse(source))
    profiles: set[tuple[str, str]] = set()
    for s in found:
        if not _is_producer(s.node, s.name) or not s.ancestors:
            continue
        parent, field = s.ancestors[-1]
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and field == "value":
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            profiles |= {(s.scope, t.id) for t in targets if isinstance(t, ast.Name)}
    hits: list[int] = []
    for s in found:
        node = s.node
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "to_dict":
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and (s.scope, receiver.id) in profiles:
            hits.append(node.lineno)
        elif isinstance(receiver, ast.Call):
            inner = next((r for r in found if r.node is receiver), None)
            if inner is not None and _is_producer(receiver, inner.name):
                hits.append(node.lineno)
    return hits


def test_no_module_writes_a_raw_profile() -> None:
    bad = {}
    for path in sorted(_SRC.rglob("*.py")):
        hits = offenders(path.read_text(encoding="utf-8"))
        if hits:
            bad[path.relative_to(_SRC).as_posix()] = hits
    assert not bad, f"serialize a profile with decoy_engine.profile_document: {bad}"


_OLD_DEMO = """\
def _demo(sample_csv, scan_json):
    import json as _json
    import pandas as pd
    from decoy_engine import profile_columns

    df = pd.read_csv(sample_csv)
    profile = profile_columns(df, source_label=sample_csv.name, sample_strategy="full")
    scan_json.write_text(_json.dumps(profile.to_dict(), indent=2))
"""


def test_the_old_demo_line_is_flagged() -> None:
    assert offenders(_OLD_DEMO) == [8]


def test_seeded_bypasses_are_flagged() -> None:
    assert offenders("import decoy_engine\np = decoy_engine.profile_columns(df)\np.to_dict()\n")
    assert offenders("from decoy_engine import profile_columns as pc\nd = pc(df).to_dict()\n")
    assert offenders(
        "from decoy_engine import profile_columns\nd = profile_columns(df).to_dict()\n"
    )


def test_the_engine_writer_and_unrelated_dicts_pass() -> None:
    fixed = _OLD_DEMO.replace("profile.to_dict()", "profile_document(profile)")
    assert offenders(fixed) == []
    # A to_dict on some other object, or on a profile name bound in another function.
    assert offenders("def f(checks):\n    return [c.to_dict() for c in checks]\n") == []
    other = (
        "from decoy_engine import profile_columns\n"
        "def a(df):\n    profile = profile_columns(df)\n"
        "def b(profile):\n    return profile.to_dict()\n"
    )
    assert offenders(other) == []
