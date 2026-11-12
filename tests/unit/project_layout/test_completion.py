"""AT-27 (P5): tab completion of a pipeline name.

Driven through Typer's own shell-completion entry point (`_DECOY_COMPLETE=complete_bash` with
`COMP_WORDS` and `COMP_CWORD`), so the project flag already typed on the line reaches the
completer the way a shell would hand it over. Bash lines read `<type>,<value>`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import typer
from typer.models import CompletionItem
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import completers

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return folder


def _project(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    for name in names:
        folder = root / "pipelines" / name
        folder.mkdir(parents=True)
        (folder / "pipeline.yaml").write_text("version: 2\n", encoding="utf-8")
    return root


def _complete(line: str, cursor: int, env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    result = runner.invoke(
        app,
        [],
        prog_name="decoy",
        env={
            "_DECOY_COMPLETE": "complete_bash",
            "COMP_WORDS": line,
            "COMP_CWORD": str(cursor),
            **(env or {}),
        },
    )
    pairs = [tuple(row.split(",", 1)) for row in result.stdout.splitlines() if "," in row]
    return [(kind, value) for kind, value in pairs]


def test_names_with_the_typed_prefix_come_with_one_file_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders", "other", "members")
    monkeypatch.chdir(root / "pipelines")
    assert _complete("decoy run o", 2) == [("plain", "orders"), ("plain", "other"), ("file", "o")]


def test_every_pipeline_parameter_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders")
    monkeypatch.chdir(root)
    for line, cursor in (
        ("decoy validate config o", 3),
        ("decoy report vault v.db --config o", 5),
        ("decoy report fidelity a.csv b.csv --config o", 6),
    ):
        assert ("plain", "orders") in _complete(line, cursor), line


def test_the_project_flag_already_on_the_line_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert _complete("decoy run o", 2) == [("file", "o")]
    assert _complete(f"decoy --project {root} run o", 4) == [("plain", "orders"), ("file", "o")]
    env = {"DECOY_PROJECT": str(root)}
    assert _complete("decoy run o", 2, env) == [("plain", "orders"), ("file", "o")]


def test_outside_a_project_only_the_file_item_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _complete("decoy run o", 2) == [("file", "o")]


@posix_only
def test_a_folder_that_links_out_of_pipelines_is_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders")
    target = tmp_path / "away"
    target.mkdir()
    (target / "pipeline.yaml").write_text("version: 2\n", encoding="utf-8")
    (root / "pipelines" / "evil").symlink_to(target, target_is_directory=True)
    monkeypatch.chdir(root)
    assert _complete("decoy run ", 2) == [("plain", "orders"), ("file", "")]


def test_a_failing_project_lookup_leaves_only_the_file_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders")
    monkeypatch.chdir(root)

    def broken(*args, **kwargs):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr("decoy.cli.io.find_project", broken)
    assert _complete("decoy run o", 2) == [("file", "o")]


def test_the_completer_returns_public_typer_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "orders")
    monkeypatch.chdir(root)
    ctx = typer.Context(typer.main.get_command(app))
    items = completers.pipeline_names(ctx, "or")
    assert all(isinstance(item, CompletionItem) for item in items)
    assert [(i.type, i.value) for i in items] == [("plain", "orders"), ("file", "or")]
