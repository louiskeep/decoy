"""One `--json` error object for every command, and errors that survive `--quiet`.

Covers the converted emitters: each prints through `emit_error`, so a failure reads the same
in `--json` (one schema-valid object) and in `--quiet` (human line on stderr, stdout empty).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from tests.command_tree import visible_paths

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "schemas" / "decoy-error-v1.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
runner = CliRunner()

BAD_YAML, BAD_CSV, BAD_JSON, GOOD_CSV = "bad.yaml", "bad.csv", "bad.json", "ok.csv"

# argv per command that fails on input the CLI accepts at parse time. `{}` paths are the files
# written by the `files` fixture.
BAD_INPUT: dict[str, list[str]] = {
    "run": ["run", BAD_YAML],
    "unmask": ["unmask", BAD_YAML, GOOD_CSV],
    "tokenize": ["tokenize", BAD_YAML, "--vault", "v.db"],
    "detokenize": ["detokenize", BAD_YAML, GOOD_CSV, "--vault", "v.db"],
    "fit": ["fit", BAD_CSV],
    "init": ["init", GOOD_CSV, "--preset", "generate", "-o", "-"],
    "explain": ["explain", "nonsense-topic"],
    "list": ["list", "nonsense"],
    "show": ["show", "nonsense"],
    "subset": ["subset", BAD_YAML],
    "validate config": ["validate", "config", BAD_YAML],
    "validate compile": ["validate", "compile", BAD_YAML],
    "project new": ["project", "new", GOOD_CSV],
    "project show": ["project", "show"],
    "scan fields": ["scan", "fields", BAD_JSON],
    "scan show": ["scan", "show", BAD_JSON, "f"],
    "scan diff": ["scan", "diff", BAD_JSON, BAD_JSON],
    "report show": ["report", "show", BAD_JSON],
    "report render": ["report", "render", BAD_JSON, "-o", "out.html"],
    "report verify": ["report", "verify", BAD_JSON],
    "report fidelity": ["report", "fidelity", BAD_CSV, GOOD_CSV],
    "report integrity": [
        "report",
        "integrity",
        GOOD_CSV,
        "--source",
        GOOD_CSV,
        "--config",
        BAD_YAML,
    ],
    "report diff": ["report", "diff", BAD_JSON, BAD_JSON],
    "report vault": ["report", "vault", GOOD_CSV, "--config", BAD_YAML],
}

# Commands with --json that have no bad input to give, or that fail outside this object today.
EXEMPT: dict[str, str] = {
    "schema": "prints a document and has no failing input",
    "doctor": "reports check results, status pass or fail, not an error object",
    "info": "prints environment facts and has no failing input",
    "project list": "lists folders and has no failing input",
    "demo": "its only inputs are range-checked by the parser",
    "validate preflight": "reports a failed check as status fail, a result not an error",
    "setup": "known gap: a failure prints human text to stderr under --json",
    "upgrade": "known gap: a failure prints human text to stderr under --json",
}


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / BAD_YAML).write_text("a: [unclosed\n", encoding="utf-8")
    (tmp_path / BAD_CSV).write_text("", encoding="utf-8")
    (tmp_path / BAD_JSON).write_text("{nope", encoding="utf-8")
    (tmp_path / GOOD_CSV).write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _leaf_commands() -> set[str]:
    import typer.main

    root = typer.main.get_command(app)
    found: set[str] = set()
    for path in visible_paths():
        cmd = root
        for part in path:
            cmd = cmd.commands[part]  # type: ignore[attr-defined]
        if not getattr(cmd, "commands", None) and any(
            "--json" in getattr(p, "opts", []) for p in cmd.params
        ):
            found.add(" ".join(path))
    return found


def test_every_json_command_has_a_bad_input_or_a_stated_exemption() -> None:
    assert set(BAD_INPUT) | set(EXEMPT) == _leaf_commands()
    assert set(BAD_INPUT).isdisjoint(EXEMPT)


@pytest.mark.parametrize("name", sorted(BAD_INPUT))
def test_bad_input_gives_one_schema_valid_error_object(files: Path, name: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")

    result = runner.invoke(app, [*BAD_INPUT[name], "--json"])

    assert result.exit_code != 0, result.output
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1, result.stdout
    payload = json.loads(lines[0])
    jsonschema.validate(payload, SCHEMA)
    assert payload["command"].split()[0] == BAD_INPUT[name][0]


def test_fit_json_keeps_the_code_out_of_the_error_text(files: Path) -> None:
    result = runner.invoke(
        app, ["fit", GOOD_CSV, "--joint-max-cells", "36", "--json"], catch_exceptions=False
    )

    assert result.exit_code == EXIT_USAGE
    payload = json.loads(result.stdout)
    assert payload["code"] == "fit_joint_max_cells_needs_joint"
    assert not payload["error"].startswith(payload["code"])
    assert "message" not in payload


def test_unmask_prints_its_error_under_quiet(files: Path) -> None:
    result = runner.invoke(app, ["unmask", BAD_YAML, GOOD_CSV, "--quiet"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "error: " in result.stderr


def test_multi_scan_prints_error_and_hint_under_quiet(files: Path) -> None:
    result = runner.invoke(app, ["scan", GOOD_CSV, GOOD_CSV, "--output", "-", "--quiet"])

    assert result.exit_code == EXIT_USAGE
    assert result.stdout == ""
    assert "error: " in result.stderr
    assert "hint: " in result.stderr


def test_gen_scaffold_prints_its_error_under_quiet(files: Path) -> None:
    result = runner.invoke(app, ["init", GOOD_CSV, "--preset", "generate", "-o", "-", "--quiet"])

    assert result.exit_code == EXIT_USAGE
    assert result.stdout == ""
    assert "error: " in result.stderr


def test_fit_prints_bracketed_text_verbatim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad[vault].csv").write_text("", encoding="utf-8")

    result = runner.invoke(app, ["fit", "bad[vault].csv"])

    assert result.exit_code != 0
    assert "bad[vault].csv" in result.stderr


def test_scan_prints_bracketed_text_verbatim(files: Path, monkeypatch) -> None:
    from decoy.cli.scanning import _multi

    def _raise(*args, **kwargs):
        raise _multi.ScanUsageError("install 'decoy-engine[vault]' first", "retry.")

    monkeypatch.setattr(_multi, "resolve_sources", _raise)

    result = runner.invoke(app, ["scan", GOOD_CSV, GOOD_CSV])

    assert result.exit_code == EXIT_USAGE
    assert "decoy-engine[vault]" in result.stderr


def test_reference_prints_bracketed_text_verbatim(files: Path) -> None:
    result = runner.invoke(app, ["show", "schema", "a[vault]b"])

    assert result.exit_code == EXIT_USAGE
    assert "a[vault]b" in result.stderr
