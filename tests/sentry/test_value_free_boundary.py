"""Build-failing sentry, part 1: the value-free boundary is exclusive by construction.

Exclusivity proofs (allowlists, not spelling denylists):

1. Structure. `pre_scan.py`, `post_scan.py` and `_projections.py` may import only an
   explicit allowlist (no `os`, `io`, `sys`, `builtins`, `subprocess`, `shutil`,
   `tempfile`, `logging`, `warnings`, `rich` or `decoy.ui.*`), may not touch an
   I/O-capable builtin or attribute, may not construct a boundary type, and may hand
   `Surface.emit` only a pure renderer. `write_saved_scan` has exactly one call site.
   Every check is proven non-vacuous by seeding each evasion and watching it go red.
2. Boundary membership. Every pre-scan/post-scan command is a `ValueFreeCommand`
   under a `ValueFreeGroup`, and refuses to run outside the boundary.
3. Semantics. `SafeStr` is the only string a projection accepts and it cannot be
   minted outside the policy constructors; a recursive auto-poisoner fuzzes every
   projection builder and every string in every output must be a `SafeStr` with no
   canary in it.

Part 2 (runtime containment, write audit and the canary corpus) is
`test_value_free_canaries.py`.
"""

from __future__ import annotations

import ast
import io
import random
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _value_free_checks as checks

from decoy.cli import _boundary as bd
from decoy.cli import _projections as proj
from decoy.cli import _value_free as vf

SRC = Path(__file__).resolve().parents[2] / "src" / "decoy" / "cli"
COMMAND_MODULES = ("pre_scan.py", "post_scan.py")
GUARDED_MODULES = (*COMMAND_MODULES, "_projections.py")

ENGINE = "QZENGINE8823"
CELL = "QZCELL9904"
LAYOUT_TXT = "QZLAYOUT4417"
POISON = f"/{ENGINE}/{CELL}"


def _source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name))


# ---------------------------------------------------------------------------
# 1. Structure: import + capability allowlist.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", GUARDED_MODULES)
def test_guarded_modules_pass_import_and_capability_allowlist(module: str) -> None:
    hits = checks.module_violations(_source(module), command=module in COMMAND_MODULES)
    assert not hits, f"{module} reaches past the value-free boundary: {hits}"


def test_contract_module_is_pure() -> None:
    """`_value_free.py` (the F31-liftable contract) does no I/O."""
    allowed = checks.PURE_IMPORTS | {"sys", "types", "decoy.cli.exit_codes"}
    tree = _tree("_value_free.py")
    hits = checks.import_violations(tree, allowed)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in checks.FORBIDDEN_ATTRS:
            hits.append(f"{node.lineno}: .{node.attr}")
        if isinstance(node, ast.Name) and node.id in {"open", "print", "input", "eval", "exec"}:
            hits.append(f"{node.lineno}: {node.id}")
    assert not hits, hits


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
                if (
                    isinstance(node, ast.Name)
                    and node.id == handler.name
                    and id(node) not in allowed
                ):
                    bad.append(f"{node.lineno}: {handler.name}")
    assert not bad, f"{module} uses a caught exception outside `exc=`: {bad}"


@pytest.mark.parametrize("module", COMMAND_MODULES)
def test_every_renderer_is_pure(module: str) -> None:
    hits = checks.emit_renderer_violations(_source(module))
    assert not hits, f"{module} renderer is not pure: {hits}"


def test_write_saved_scan_has_exactly_one_call_site() -> None:
    sources = {p.name: p.read_text(encoding="utf-8") for p in SRC.rglob("*.py")}
    sites = checks.saved_scan_call_sites(sources)
    assert [name for name, _ in sites] == ["pre_scan.py"], sites


# ---------------------------------------------------------------------------
# 1b. Non-vacuity: each seeded evasion turns the structural sentry red.
# ---------------------------------------------------------------------------

SEEDED_EVASIONS = {
    "path_open_write": 'def _x(x):\n    Path("x").open("w").write(x)\n',
    "io_open": 'import io\nio.open("x", "w")\n',
    "os_write": 'import os\nos.write(1, b"x")\n',
    "builtins_print": 'import builtins\nbuiltins.print("x")\n',
    "getattr_write_text": 'getattr(Path("x"), "write_text")("x")\n',
    "import_subprocess": "import subprocess\n",
    "from_subprocess": "from subprocess import run\n",
    "import_logging": "import logging\n",
    "import_warnings": "import warnings\n",
    "import_rich": "from rich.console import Console\n",
    "import_ui": "from decoy.ui.output import setup_output\n",
    "import_shutil": "import shutil\n",
    "import_tempfile": "import tempfile\n",
    "sys_stdout": 'import sys\nsys.stdout.write("x")\n',
    "print": 'print("x")\n',
    "dunder_import": '__import__("os").write(1, b"x")\n',
    "mint_token": 'vf.SafeStr("x", vf._MINT)\n',
    "mint_private": 'vf._mint_str("x")\n',
    "construct_surface": 'bd.Surface("pre-scan", None, None, False, False, False)\n',
    "construct_printer": "Printer(None, None)\n",
    "private_stream": 'surface._out.write("x")\n',
    "private_state": "surface._state.console.print(1)\n",
    "dataframe_writer": 'df.to_csv("x")\n',
    "json_dump": "_json.dump({}, fh)\n",
    "typer_echo": 'typer.echo("x")\n',
    "boundary_internal": "from decoy.cli._boundary import _ACTIVE\n",
    "relative_import": "from . import _boundary\n",
}


@pytest.mark.parametrize("module", GUARDED_MODULES)
@pytest.mark.parametrize("label", sorted(SEEDED_EVASIONS))
def test_sentry_catches_seeded_evasions(module: str, label: str) -> None:
    seeded = _source(module) + "\n" + SEEDED_EVASIONS[label]
    assert checks.module_violations(seeded, command=module in COMMAND_MODULES), label


@pytest.mark.parametrize(
    ("module", "snippet"),
    [
        ("post_scan.py", 'surface.write_saved_scan(Path("x"), {})\n'),
        ("pre_scan.py", 'surface.write_saved_scan(Path("y"), {})\n'),
        ("_boundary.py", 'Surface.write_saved_scan(None, Path("z"), {})\n'),
        ("post_scan.py", "fn = surface.write_saved_scan\n"),
        ("post_scan.py", 'getattr(surface, "write_saved_scan")\n'),
    ],
)
def test_saved_scan_lock_catches_a_second_call_site(module: str, snippet: str) -> None:
    sources = {p.name: p.read_text(encoding="utf-8") for p in SRC.rglob("*.py")}
    sources[module] += "\n" + snippet
    names = [name for name, _ in checks.saved_scan_call_sites(sources)]
    assert names != ["pre_scan.py"], names


IMPURE_RENDERERS = {
    "global_read": "SECRET = 1\ndef _r(p, body):\n    p.line(SECRET)\n",
    "fstring": 'def _r(p, body):\n    p.line(p.t(f"{body}"))\n',
    "data_template": 'def _r(p, body):\n    p.line(p.t(body["name"]))\n',
    "data_separator": 'def _r(p, body):\n    p.line(p.join(body["sep"], []))\n',
    "data_header": 'def _r(p, body):\n    p.table(body["h"], rows=[])\n',
    "data_style": 'def _r(p, body):\n    p.line(p.t("x", style=body["s"]))\n',
    "data_card_status": 'def _r(p, body):\n    p.card("c", [], None, body["s"])\n',
    "str_method": 'def _r(p, body):\n    p.line(body["name"].upper())\n',
    "str_builtin": "def _r(p, body):\n    p.line(str(body))\n",
    "private_printer": "def _r(p, body):\n    p._Printer__state.console.print(body)\n",
    "nested_def": "def _r(p, body):\n    def inner():\n        return 1\n    p.line(inner())\n",
    "lambda": "def _r(p, body):\n    p.line((lambda: 1)())\n",
    "not_p": "def _r(out, body):\n    out.line()\n",
    "impure_helper": "def _h(p):\n    print(1)\ndef _r(p, body):\n    _h(p)\n",
    "global_stmt": "X = 0\ndef _r(p, body):\n    global X\n    p.line()\n",
}


@pytest.mark.parametrize("label", sorted(IMPURE_RENDERERS))
def test_renderer_check_catches_impure_renderers(label: str) -> None:
    source = IMPURE_RENDERERS[label] + 'surface.emit(x, status="ok", render=_r)\n'
    assert checks.emit_renderer_violations(source), label


def test_renderer_check_rejects_non_name_render() -> None:
    assert checks.emit_renderer_violations('surface.emit(x, status="ok", render=lambda p, b: 1)\n')


# ---------------------------------------------------------------------------
# 2. Boundary membership.
# ---------------------------------------------------------------------------


def test_every_command_runs_inside_the_boundary() -> None:
    import typer

    from decoy.__main__ import app

    root = typer.main.get_command(app)
    for name in ("pre-scan", "post-scan"):
        group = root.commands[name]  # type: ignore[attr-defined]
        assert type(group).__name__ == "ValueFreeGroup", name
        assert group.commands
        for leaf in group.commands.values():
            assert isinstance(leaf, bd.ValueFreeCommand), (name, leaf.name)


def test_callbacks_refuse_to_run_outside_the_boundary() -> None:
    from decoy.cli import post_scan, pre_scan

    with pytest.raises(RuntimeError):
        bd.surface("pre-scan", json_=False, quiet=False, verbose=False)
    with pytest.raises(RuntimeError):
        pre_scan._fields(scan="-", pii=None, quasi=False, json_=False, quiet=False, verbose=False)
    with pytest.raises(RuntimeError):
        post_scan._integrity(
            masked=Path("m"), source=Path("s"), config=None, out=None,
            allow_source_mismatch=False, json_=False, quiet=False, verbose=False,
        )  # fmt: skip


def test_projection_cannot_be_forged_and_raw_dicts_cannot_be_emitted(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        vf.Projection("x/v1", {"a": 1})
    surface = bd.Surface("pre-scan", io.StringIO(), io.StringIO(), True, False, False)
    for call in (
        lambda: surface.emit({"raw": ENGINE}, status="ok"),  # type: ignore[arg-type]
        lambda: surface.stream({"raw": ENGINE}),  # type: ignore[arg-type]
        lambda: surface.write_report(tmp_path / "r.json", {"raw": ENGINE}),  # type: ignore[arg-type]
    ):
        with pytest.raises(TypeError):
            call()
    with pytest.raises(TypeError):
        vf.mint("x/v1", {"bad": object()})
    with pytest.raises(TypeError):
        vf.mint("pre-scan-fields/v1", {"matched": object()})


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
    text = _source("_projections.py")
    for key in ('"message"', '"detail"', '"source_label"', '"sample_invalid"', '"samples"'):
        assert f".get({key})" not in text and f"[{key}]" not in text, key
    # Raw value containers may only be tested for presence, never read.
    assert text.count('"top_values"') == text.count('bool(field.get("top_values"))') == 1


# ---------------------------------------------------------------------------
# 3. Semantics: SafeStr is a closed type.
# ---------------------------------------------------------------------------


def test_safestr_is_minted_only_by_policy_constructors() -> None:
    for args in (("x",), ("x", object()), ("x", None)):
        with pytest.raises(TypeError):
            vf.SafeStr(*args)
    assert type(vf.literal("ok")) is vf.SafeStr
    assert vf.vocab(f"{ENGINE}", frozenset({"a"})) == vf.UNRECOGNIZED
    assert vf.clean_name(POISON) is None
    assert vf.iso_timestamp(ENGINE) is None
    with pytest.raises(ValueError):
        vf.opaque_label(ENGINE, 1)
    with pytest.raises(ValueError):
        vf.join_safe(ENGINE, [])


@pytest.mark.parametrize(
    "body",
    [
        {"matched": "raw_plain_str"},
        {"matched": vf.literal("a") + "b"},  # derived strings are plain str
        {"matched": f"{vf.literal('a')}"},
        {"matched": vf.literal("a").upper()},
        {"fields": [{"name": "raw"}]},
        {ENGINE: 1},  # plain key outside the schema
        {"fields": [{vf.literal("Bad Key"): 1}]},  # minted key outside the key grammar
        {"matched": float("nan")},
    ],
)
def test_mint_refuses_plain_str_unknown_keys_and_non_finite(body: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        vf.mint("pre-scan-fields/v1", body)


def test_mint_refuses_unknown_schema() -> None:
    with pytest.raises(TypeError):
        vf.mint(f"{ENGINE}/v1", {})


def test_printer_refuses_plain_strings_and_data_templates() -> None:
    out = io.StringIO()
    surface = bd.Surface("pre-scan", out, io.StringIO(), False, False, False)
    projection = vf.mint("pre-scan-fields/v1", {"matched": 0, "total": 0, "fields": []})
    attempts = [
        lambda p, b: p.line("raw"),
        lambda p, b: p.t(vf.literal("{}")),  # a SafeStr cannot pose as a template
        lambda p, b: p.t("{}", "raw"),
        lambda p, b: p.t("x", style=ENGINE),
        lambda p, b: p.table("h", rows=[("raw",)]),
        lambda p, b: p.card("c", [("label", 1)], None, "ok"),
        lambda p, b: p.line(object()),
    ]
    for render in attempts:
        with pytest.raises((TypeError, ValueError, KeyError)):
            surface.emit(projection, status="ok", render=render)
    with pytest.raises(TypeError):
        bd.Printer(None, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        bd.Fragment(None, object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        surface.emit(projection, status=ENGINE)


def test_type_names_are_allowlisted_static_classes() -> None:
    import json

    import yaml

    assert vf.safe_cls_name(ValueError) == "ValueError"
    assert vf.safe_cls_name(json.JSONDecodeError) == "JSONDecodeError"
    assert vf.safe_cls_name(yaml.YAMLError) == "YAMLError"
    dynamic = type(f"Err_{CELL}", (Exception,), {})
    assert vf.safe_cls_name(dynamic) == "Exception"
    posing = type(f"Err_{CELL}", (Exception,), {"__module__": "decoy_engine.errors"})
    assert vf.safe_cls_name(posing) == "Exception"
    warn = type(f"Warn_{CELL}", (UserWarning,), {})
    assert vf.safe_cls_name(warn, "Warning") == "Warning"
    assert vf.safe_cls_name(UserWarning, "Warning") == "UserWarning"
    assert vf.known_type_name("ValueError") == "ValueError"
    assert vf.known_type_name(f"Err_{CELL}") == "Exception"
    assert vf.known_type_name(f"{ENGINE}: {CELL}") == "Exception"


# ---- recursive auto-poisoner -------------------------------------------------------------------


class _Poison(dict):
    """Every lookup returns a seeded mix of dirty canary strings, nested poisoners, lists
    and junk numbers, so every key a builder reads -- known or not -- is poisoned."""

    def __init__(self, rng: random.Random, depth: int = 0) -> None:
        super().__init__()
        self._rng, self._depth = rng, depth

    def _make(self, key: Any) -> Any:
        r = self._rng.random()
        if self._depth > 3 or r < 0.3:
            return f"{POISON}:{key}"
        if r < 0.45:
            return _Poison(self._rng, self._depth + 1)
        if r < 0.65:
            return [_Poison(self._rng, self._depth + 1) for _ in range(self._rng.randint(1, 3))]
        if r < 0.75:
            return [f"{POISON}:{key}:{i}" for i in range(2)]
        return self._rng.choice(
            [float("nan"), float("inf"), -1, True, 2.5, 10**30, None, f"unknown_kind:{POISON}"]
        )

    def get(self, key: Any, default: Any = None) -> Any:
        if not dict.__contains__(self, key):
            dict.__setitem__(self, key, self._make(key))
        return dict.__getitem__(self, key)

    def __getitem__(self, key: Any) -> Any:
        return self.get(key)

    def __contains__(self, key: object) -> bool:
        return True


def _walk_strings(value: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict) or hasattr(value, "items"):
        for k, v in value.items():
            found.extend(_walk_strings(k))
            found.extend(_walk_strings(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            found.extend(_walk_strings(v))
    return found


def _assert_all_safe(projection: vf.Projection) -> int:
    strings = _walk_strings(projection.body)
    for s in strings:
        assert type(s) is vf.SafeStr or s in vf.SCHEMAS[projection.schema], repr(s)
        assert ENGINE not in s and CELL not in s, s
    return len(strings)


BUILDERS = {
    "profile": lambda r: proj.profile(_Poison(r), include_fields=True, saved=r.random() < 0.5),
    "field_list": lambda r: proj.field_list(
        _Poison(r), pii=r.choice([None, "high", "none"]), quasi=r.random() < 0.5
    ),
    "field_detail": lambda r: proj.field_detail(_Poison(r), _Poison(r)),
    "scan_diff": lambda r: proj.scan_diff(_Poison(r), _Poison(r)),
    "integrity_report": lambda r: proj.integrity_report(_Poison(r)),
    "fidelity_report": lambda r: proj.fidelity_report(_Poison(r), _Poison(r)),
}


@pytest.mark.parametrize("builder", sorted(BUILDERS))
def test_projection_builders_fuzzed_with_auto_poisoner(builder: str) -> None:
    total = 0
    for seed in range(150):
        total += _assert_all_safe(BUILDERS[builder](random.Random(seed)))
    assert total > 0, f"{builder}: the fuzz never produced a string to check"


def test_closest_field_suggestion_is_policed() -> None:
    for seed in range(50):
        rng = random.Random(seed)
        scan = {"fields": [{"name": f"{POISON}:{i}"} for i in range(3)] + [_Poison(rng)]}
        hint = proj.closest_field(scan, f"{POISON}:1")
        assert hint is None or (
            type(hint) is vf.SafeStr and CELL not in hint and ENGINE not in hint
        )


def test_fuzz_is_not_vacuous(monkeypatch: pytest.MonkeyPatch) -> None:
    """A policy that let data through is caught: by `mint` for a plain str, by the
    canary scan for a string wrongly minted."""
    monkeypatch.setattr(proj, "vocab", lambda value, allowed: value)
    with pytest.raises(TypeError):
        for seed in range(20):
            BUILDERS["integrity_report"](random.Random(seed))
    monkeypatch.undo()
    monkeypatch.setattr(vf, "is_clean_name", lambda value: isinstance(value, str))
    with pytest.raises(AssertionError):
        for seed in range(20):
            _assert_all_safe(BUILDERS["profile"](random.Random(seed)))
