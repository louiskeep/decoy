"""F30 C-T8: the CLI's OpenTelemetry surface stays closed (Platform P-T12 rules, f30r3).

AST over `src/decoy`. `opentelemetry` is imported only by `src/decoy/telemetry.py`; inside
it no span call omits `record_exception=False, set_status_on_exception=False`, status is a
bare `StatusCode.ERROR`/`OK`, nothing records exceptions, events or links, installs a global
provider, reads `OTEL_*` through the SDK, shuts the provider down, or sends through a
`requests.Session` (which resolves redirects and reads the body, Codex f30r3 V1-1); every
adapter `.send(` streams. Each rule has a seeded fixture under fixtures/otel_closed/.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
TELEMETRY = SRC / "telemetry.py"
FIXTURES = Path(__file__).parent / "fixtures" / "otel_closed"
RULES = (
    "import_outside", "span_keywords", "status_arg", "status_ctor", "record_exception",
    "add_event", "add_link", "set_tracer_provider", "resource_create", "otlp_exporter",
    "parse_env_headers", "instrumentation", "shutdown", "session_request",
    "adapter_send_stream",
)  # fmt: skip
SPAN_CALLS = {"start_span", "start_as_current_span", "use_span"}
BANNED_NAMES = {
    "set_tracer_provider": "set_tracer_provider",
    "OTLPSpanExporter": "otlp_exporter",
    "parse_env_headers": "parse_env_headers",
}


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _false_kw(call: ast.Call, name: str) -> bool:
    return any(
        k.arg == name and isinstance(k.value, ast.Constant) and k.value.value is False
        for k in call.keywords
    )


def _imports(tree: ast.AST) -> list[str]:
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods += [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
    return mods


def violations(source: str, *, is_telemetry: bool) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    mods = _imports(tree)
    if not is_telemetry:
        if any(m.split(".")[0] == "opentelemetry" for m in mods):
            found.add("import_outside")
        return found
    if any(m.startswith("opentelemetry.instrumentation") for m in mods):
        found.add("instrumentation")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute, ast.alias)):
            ident = node.name.rsplit(".", 1)[-1] if isinstance(node, ast.alias) else _name(node)
            if ident in BANNED_NAMES:
                found.add(BANNED_NAMES[ident])
        if not isinstance(node, ast.Call):
            continue
        fn, attr = node.func, _name(node.func)
        receiver = _name(fn.value) if isinstance(fn, ast.Attribute) else ""
        if attr in SPAN_CALLS and not (
            _false_kw(node, "record_exception") and _false_kw(node, "set_status_on_exception")
        ):
            found.add("span_keywords")
        if attr == "set_status" and not (
            len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Attribute)
            and _name(node.args[0].value) == "StatusCode"
            and node.args[0].attr in {"ERROR", "OK"}
        ):
            found.add("status_arg")
        if attr == "Status":
            found.add("status_ctor")
        if attr in {"record_exception", "add_event", "add_link"}:
            found.add(attr)
        if attr == "create" and receiver == "Resource":
            found.add("resource_create")
        if attr == "shutdown" and "exporter" not in receiver.lower():
            found.add("shutdown")
        if attr in {"Session", "post", "request"} or (
            receiver == "requests" and attr in {"get", "put"}
        ):
            found.add("session_request")
        if attr == "send" and not any(
            k.arg == "stream" and isinstance(k.value, ast.Constant) and k.value.value is True
            for k in node.keywords
        ):
            found.add("adapter_send_stream")
    return found


def test_opentelemetry_only_in_telemetry_module() -> None:
    offenders = {
        str(path.relative_to(ROOT)): sorted(found)
        for path in SRC.rglob("*.py")
        if (found := violations(path.read_text(encoding="utf-8"), is_telemetry=path == TELEMETRY))
    }
    assert TELEMETRY.is_file()
    assert offenders == {}


def test_telemetry_module_imports_opentelemetry() -> None:
    mods = _imports(ast.parse(TELEMETRY.read_text(encoding="utf-8")))
    assert any(m.startswith("opentelemetry.sdk") for m in mods)


@pytest.mark.parametrize("rule", RULES)
def test_seeded_fixture_is_red(rule: str) -> None:
    source = (FIXTURES / f"{rule}.py").read_text(encoding="utf-8")
    assert rule in violations(source, is_telemetry=rule != "import_outside")
