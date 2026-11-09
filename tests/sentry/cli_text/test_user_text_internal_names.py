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
from pathlib import Path

import pytest
import typer
import typer.core
from tests.sentry.cli_text._banned_text import (
    ALLOWLIST,
    BANNED_USER_TEXT,
    CTX_GROUP_ARG,
    CTX_NAME_KWARG,
)
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import explain as explain_mod

SRC = Path(__file__).resolve().parents[3] / "src" / "decoy"
runner = CliRunner()


def _hits(text: str, exempt: frozenset[str] = frozenset()) -> list[str]:
    return [p.pattern for p in BANNED_USER_TEXT if p.pattern not in exempt and p.search(text)]


def _walk(cmd: typer.core.TyperCommand, path: tuple[str, ...] = ()):
    """Yield (path, command) for the whole tree, hidden commands included."""
    yield path, cmd
    if isinstance(cmd, typer.core.TyperGroup):
        for name, sub in cmd.commands.items():
            yield from _walk(sub, (*path, name))


def _tree_texts(root: typer.core.TyperCommand | None = None) -> list[tuple[str, str]]:
    root = root or typer.main.get_command(app)
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
        label = "decoy " + " ".join(path)
        assert result.exit_code == 0, f"{label} --help exited {result.exit_code}"
        assert "Usage:" in result.output, f"{label} --help printed no usage line"
        out.append((f"decoy {' '.join(path)} --help", result.output))
    return out


def _usage_texts(tmp_path: Path) -> list[tuple[str, str]]:
    out = []
    for group, name in (("scan", "nofile.csv"), ("validate", "nofile.yaml")):
        result = runner.invoke(app, [group, str(tmp_path / name)])
        assert "Usage:" in result.output, f"decoy {group} printed no usage line"
        assert f"decoy {group}" in result.output, f"usage does not carry `decoy {group}`"
        out.append((f"usage of decoy {group}", result.output))
    return out


def _explain_texts() -> list[tuple[str, str]]:
    out = []
    for name, topic in explain_mod._TOPICS.items():
        out.append((f"explain {name} summary", topic.summary))
        out.append((f"explain {name} body", topic.body))
        out.extend((f"explain {name} see_also", s) for s in topic.see_also)
    return out


def _contexts(tree: ast.AST) -> dict[int, str]:
    """Map id(Constant node) -> the allowlistable AST context it sits in."""
    ctx: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if fname == "make_default_group" and node.args and isinstance(node.args[0], ast.Constant):
            ctx[id(node.args[0])] = CTX_GROUP_ARG
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                ctx[id(kw.value)] = CTX_NAME_KWARG
    return ctx


def _string_constants(source: str) -> list[tuple[int, str, str]]:
    """(lineno, text, context) for every string constant outside docstrings."""
    tree = ast.parse(source)
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
    ctx = _contexts(tree)
    return [
        (node.lineno, node.value, ctx.get(id(node), ""))
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


Allowlist = dict[tuple[str, str, str, str], tuple[int, str]]


def _constant_hits(
    rel: str, text: str, context: str, allowlist: Allowlist = ALLOWLIST
) -> list[str]:
    """Banned patterns a constant trips. An entry exempts one pattern for one exact string in one
    AST context of one file."""
    exempt = frozenset(
        pat
        for (path, exact, pat, ctx) in allowlist
        if path == rel and exact == text and ctx == context
    )
    return _hits(text, exempt)


def _exempted_sites(rel: str, source: str, allowlist: Allowlist = ALLOWLIST) -> dict[tuple, int]:
    """Count, per allowlist key, the constants in `source` that the key exempts."""
    counts: dict[tuple, int] = {}
    for _, text, context in _string_constants(source):
        for key in allowlist:
            path, exact, _pat, ctx = key
            if path == rel and exact == text and ctx == context:
                counts[key] = counts.get(key, 0) + 1
    return counts


def _source_offenders(rel: str, source: str, allowlist: Allowlist = ALLOWLIST) -> list[str]:
    out = [
        f"{rel}:{lineno}: {hits}"
        for lineno, text, context in _string_constants(source)
        if (hits := _constant_hits(rel, text, context, allowlist))
    ]
    counts = _exempted_sites(rel, source, allowlist)
    for key, (expected, _reason) in allowlist.items():
        if key[0] == rel and counts.get(key, 0) != expected:
            out.append(
                f"{rel}: allowlist {key[1:]} matched {counts.get(key, 0)} sites, expected {expected}"
            )
    return out


def _constant_offenders() -> list[str]:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        offenders.extend(_source_offenders(rel, path.read_text(encoding="utf-8")))
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
    assert all(reason.strip() and count >= 1 for count, reason in ALLOWLIST.values())


def test_allowlist_entries_match_real_sites_in_the_expected_number() -> None:
    patterns = {p.pattern for p in BANNED_USER_TEXT}
    for (_rel, _exact, pattern, _ctx), _val in ALLOWLIST.items():
        assert pattern in patterns, pattern
    for rel in {key[0] for key in ALLOWLIST}:
        source = (SRC / rel).read_text(encoding="utf-8")
        counts = _exempted_sites(rel, source)
        for key, (expected, _reason) in ALLOWLIST.items():
            if key[0] == rel:
                assert counts.get(key, 0) == expected, key


def test_bite_a_ticket_id_in_a_help_string_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        explain_mod._TOPICS,
        "modes",
        explain_mod._Topic(name="modes", summary="Modes (FC-1)", body="x"),
    )
    assert _offenders(_explain_texts())


def test_bite_a_banned_string_constant_is_caught() -> None:
    source = 'MSG = "see FC-1 for details"\n\ndef f():\n    """DE-02 in a docstring is fine."""\n'
    offenders = _source_offenders("cli/synthetic.py", source)
    assert len(offenders) == 1
    assert offenders[0].startswith("cli/synthetic.py:1:")


def test_bite_a_banned_token_in_click_command_help_is_caught() -> None:
    synthetic = typer.Typer()

    @synthetic.command(help="Runs the thing (DE-02).")
    def one(flag: bool = typer.Option(False, help="Toggles FC-1 mode")) -> None: ...

    @synthetic.command()
    def two() -> None: ...

    offenders = _offenders(_tree_texts(typer.main.get_command(synthetic)))
    assert any("DE-" in o for o in offenders)
    assert any("FC-" in o for o in offenders)


def test_allowlist_exempts_only_the_exact_string_in_its_context() -> None:
    assert _constant_hits("cli/scan.py", "_scan", CTX_GROUP_ARG) == []
    assert _constant_hits("cli/scan.py", "_scan", CTX_NAME_KWARG) == []
    assert _constant_hits("cli/validate.py", "_gate", CTX_NAME_KWARG) == []
    # Per file, and per context: the same text elsewhere still fails.
    assert _constant_hits("cli/other.py", "_scan", CTX_NAME_KWARG)
    assert _constant_hits("cli/validate.py", "_scan", CTX_NAME_KWARG)
    assert _constant_hits("cli/scan.py", "_scan", "")


def test_bite_near_miss_of_an_allowlisted_string_still_fails() -> None:
    leak = "the post_scan step failed (DE-02, FC-1)"
    assert _constant_hits("cli/scan.py", leak, "")
    assert _constant_hits("cli/scan.py", "run _scan now", CTX_NAME_KWARG)
    assert _source_offenders("cli/scan.py", f"_LEAK = {leak!r}\n")


_REAL_SITES = (
    'x = typer.Typer(cls=make_default_group("_scan"))\n'
    'y = app.command(name="_scan", hidden=True)(f)\n'
)


def test_bite_a_second_bare_literal_of_the_allowlisted_text_is_reported() -> None:
    assert _source_offenders("cli/scan.py", _REAL_SITES) == []
    probe = 'REGISTER = "_scan"\nUSER_ERROR = "_scan"\n'
    offenders = _source_offenders("cli/scan.py", probe)
    assert any(o.startswith("cli/scan.py:1:") for o in offenders)
    assert any(o.startswith("cli/scan.py:2:") for o in offenders)
    # A bare extra literal next to the two real sites is reported on its own line.
    extra = _source_offenders("cli/scan.py", _REAL_SITES + 'USER_ERROR = "_scan"\n')
    assert len(extra) == 1 and extra[0].startswith("cli/scan.py:3:")


def test_bite_a_duplicate_name_kwarg_changes_the_site_count() -> None:
    dup = _REAL_SITES + 'z = app.command(name="_scan")(g)\n'
    offenders = _source_offenders("cli/scan.py", dup)
    assert any("matched 2 sites, expected 1" in o for o in offenders)
    # The same entry also fails when a real site disappears.
    assert any("matched 0 sites" in o for o in _source_offenders("cli/scan.py", "x = 1\n"))


def test_bite_exempt_string_with_a_second_banned_pattern_fails_on_that_pattern() -> None:
    synthetic = {("cli/synthetic.py", "_scan (FC-1)", r"(?<!\w)_scan\b", CTX_NAME_KWARG): (1, "t")}
    hits = _constant_hits("cli/synthetic.py", "_scan (FC-1)", CTX_NAME_KWARG, synthetic)
    assert hits == [r"FC-\d"]
