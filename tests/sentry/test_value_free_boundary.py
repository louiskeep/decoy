"""Static guard: pre-scan / post-scan reach every surface only through `_value_free`.

`decoy.cli._value_free` is the single sink for output, error rendering and file
writes. These modules may not print, write or format an exception or a path on
their own; a violation fails the build instead of waiting for a seeded-secret
test to happen to cover the new site.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[2] / "src" / "decoy" / "cli"
MODULES = ("pre_scan.py", "post_scan.py")

# Calls that reach a surface directly. `vf.out/err/emit/stream/card/write_artifact` are the sinks.
FORBIDDEN_CALL_ATTRS = {"print", "write_text", "write_bytes", "echo", "format_exc", "print_exc"}
FORBIDDEN_CALL_NAMES = {"print", "emit_json", "render_card", "open"}
SINK_CALLS = {"fail", "fail_runtime"}
# Names bound to a source/output/config path or option value; never formatted into text.
PATH_LIKE_NAMES = {
    "source", "output", "masked", "out", "layout", "layout_path", "report_out", "pipeline_config",
    "config", "policy", "scan", "scan_path", "old", "new", "path", "out_path", "declared_path",
    "field", "joint", "spec", "min_grade", "mode", "table_name",
}  # fmt: skip


def _parse(name: str) -> ast.Module:
    return ast.parse((CLI / name).read_text(encoding="utf-8"))


def _is_vf_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "vf"
    )


def _handler_names(tree: ast.Module) -> set[str]:
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}


@pytest.mark.parametrize("module", MODULES)
def test_no_direct_surface_access(module: str) -> None:
    offenders = []
    for node in ast.walk(_parse(module)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in FORBIDDEN_CALL_ATTRS:
            offenders.append((node.lineno, f".{fn.attr}(...)"))
        elif isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALL_NAMES:
            offenders.append((node.lineno, f"{fn.id}(...)"))
        elif (
            isinstance(fn, ast.Attribute)
            and fn.attr == "write"
            and isinstance(fn.value, ast.Attribute)
            and fn.value.attr in {"stdout", "stderr"}
        ):
            offenders.append((node.lineno, f"{fn.value.attr}.write(...)"))
    assert not offenders, f"{module}: route through decoy.cli._value_free: {offenders}"


@pytest.mark.parametrize("module", MODULES)
def test_exception_objects_are_never_rendered(module: str) -> None:
    tree = _parse(module)
    handler_vars = _handler_names(tree)
    offenders = []
    for node in ast.walk(tree):
        # str(exc) / repr(exc) / f"{exc}" / exc.args / exc.message
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"str", "repr"}
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in handler_vars
        ):
            offenders.append((node.lineno, f"{node.func.id}({node.args[0].id})"))
        if isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name):
            if node.value.id in handler_vars:
                offenders.append((node.lineno, f"f-string of {node.value.id}"))
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in handler_vars
            and node.attr in {"args", "message", "msg", "filename", "strerror", "doc"}
        ):
            offenders.append((node.lineno, f"{node.value.id}.{node.attr}"))
    assert not offenders, f"{module}: use vf.exc_label(exc) only: {offenders}"


@pytest.mark.parametrize("module", MODULES)
def test_fstrings_never_interpolate_paths_or_option_values(module: str) -> None:
    offenders = []
    for node in ast.walk(_parse(module)):
        if isinstance(node, ast.FormattedValue):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Name) and sub.id in PATH_LIKE_NAMES:
                    offenders.append((node.lineno, sub.id))
    assert not offenders, f"{module}: path/option value formatted into text: {offenders}"


@pytest.mark.parametrize("module", MODULES)
def test_error_messages_interpolate_only_boundary_helpers(module: str) -> None:
    offenders = []
    for node in ast.walk(_parse(module)):
        if not (_is_vf_call(node) and node.func.attr in SINK_CALLS):  # type: ignore[attr-defined]
            continue
        for arg in [*node.args, *(k.value for k in node.keywords)]:  # type: ignore[attr-defined]
            for fv in (n for n in ast.walk(arg) if isinstance(n, ast.FormattedValue)):
                if not _is_vf_call(fv.value) and not (
                    isinstance(fv.value, ast.Name) and fv.value.id == "detail"
                ):
                    offenders.append((fv.lineno, ast.unparse(fv.value)))
    assert not offenders, f"{module}: interpolate vf.* helper output only: {offenders}"


def test_command_modules_import_no_raw_sinks() -> None:
    for module in MODULES:
        for node in ast.walk(_parse(module)):
            if isinstance(node, ast.ImportFrom) and node.module in {"decoy.ui.output", "decoy.ui.card"}:
                names = {a.name for a in node.names}
                assert not names & {"emit_json", "render_card"}, f"{module}: {names}"
