"""AT-S2: no user-visible string carries an internal name.

A first-time user read ticket ids (`FC-1`, `DE-02`), a private module path and a hidden command
name (`_scan`) in help, usage lines, `explain` topics, error text and bundled templates. The
patterns live in `_banned_text.BANNED_USER_TEXT`; this sentry applies them to:

* every command in the Click tree, hidden ones included: help, short help, epilog, option help;
* the rendered `--help` of every visible command and the usage line of a real dispatch;
* every `explain` topic summary, body and see-also line;
* every string constant under `src/decoy/**/*.py` except docstrings (AST);
* every bundled `src/decoy/templates/*.yaml`.

Comments and docstrings keep their ids: no user reads them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import typer
import typer.core
from tests.sentry.cli_text._banned_text import ALLOWLIST, BANNED_USER_TEXT
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import explain as explain_mod

SRC = Path(__file__).resolve().parents[3] / "src" / "decoy"
runner = CliRunner()


def _hits(text: str) -> list[str]:
    return [p.pattern for p in BANNED_USER_TEXT if p.search(text)]


def _walk(cmd: typer.core.TyperCommand, path: tuple[str, ...] = ()):
    """Yield (path, command) for the whole tree, hidden commands included."""
    yield path, cmd
    if isinstance(cmd, typer.core.TyperGroup):
        for name, sub in cmd.commands.items():
            yield from _walk(sub, (*path, name))


def _tree_texts() -> list[tuple[str, str]]:
    root = typer.main.get_command(app)
    out: list[tuple[str, str]] = []
    for path, cmd in _walk(root):
        label = "decoy " + " ".join(path)
        for field in ("help", "short_help", "epilog"):
            value = getattr(cmd, field, None)
            if value:
                out.append((f"{label} {field}", value))
        for param in cmd.params:
            help_text = getattr(param, "help", None)
            if help_text:
                out.append((f"{label} option {param.name}", help_text))
    return out


def _rendered_help_texts() -> list[tuple[str, str]]:
    root = typer.main.get_command(app)
    out: list[tuple[str, str]] = []
    for path, cmd in _walk(root):
        if getattr(cmd, "hidden", False):
            continue
        result = runner.invoke(app, [*path, "--help"], terminal_width=200)
        out.append((f"decoy {' '.join(path)} --help", result.output))
    return out


def _usage_texts(tmp_path: Path) -> list[tuple[str, str]]:
    out = []
    for group, name in (("scan", "nofile.csv"), ("validate", "nofile.yaml")):
        result = runner.invoke(app, [group, str(tmp_path / name)])
        out.append((f"usage of decoy {group}", result.output))
    return out


def _explain_texts() -> list[tuple[str, str]]:
    out = []
    for name, topic in explain_mod._TOPICS.items():
        out.append((f"explain {name} summary", topic.summary))
        out.append((f"explain {name} body", topic.body))
        out.extend((f"explain {name} see_also", s) for s in topic.see_also)
    return out


def _string_constants(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _allowed(rel: str, text: str) -> bool:
    return any(rel == path and fragment in text for (path, fragment) in ALLOWLIST)


def _constant_offenders() -> list[str]:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for lineno, text in _string_constants(path):
            if _hits(text) and not _allowed(rel, text):
                offenders.append(f"{rel}:{lineno}: {_hits(text)}")
    return offenders


def _template_offenders() -> list[str]:
    offenders = []
    for path in sorted((SRC / "templates").glob("*.yaml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _hits(line):
                offenders.append(f"templates/{path.name}:{lineno}: {_hits(line)}")
    return offenders


def _offenders(items: list[tuple[str, str]]) -> list[str]:
    return [f"{label}: {_hits(text)}" for label, text in items if _hits(text)]


def test_click_tree_text_names_no_internal_id() -> None:
    assert not _offenders(_tree_texts())


def test_rendered_help_names_no_internal_id() -> None:
    assert not _offenders(_rendered_help_texts())


def test_usage_lines_name_no_hidden_command(tmp_path: Path) -> None:
    assert not _offenders(_usage_texts(tmp_path))


def test_explain_topics_name_no_internal_id() -> None:
    assert not _offenders(_explain_texts())


def test_string_constants_name_no_internal_id() -> None:
    offenders = _constant_offenders()
    assert not offenders, "\n".join(offenders)


def test_bundled_templates_name_no_internal_id() -> None:
    offenders = _template_offenders()
    assert not offenders, "\n".join(offenders)


def test_allowlist_entries_carry_a_reason() -> None:
    assert all(reason.strip() for reason in ALLOWLIST.values())


def test_bite_a_ticket_id_in_a_help_string_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        explain_mod._TOPICS,
        "modes",
        explain_mod._Topic(name="modes", summary="Modes (FC-1)", body="x"),
    )
    assert _offenders(_explain_texts())
    assert re.search(r"FC-\d", "(FC-1)")
