"""AT-24 and AT-25 (P6): `decoy project new`, `show` and `list`.

`new` makes the four entries of a project (marker, `pipelines/`, `out/` with its `.gitignore`,
`.decoy/` with its `.gitignore`) and fills only what is missing on a second call. `show` lists the
selected project's members with the newest run and the last clean run read from the folders;
`list` finds projects one level down. Both take `--json`.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import DECOY_DIR, find_project
from decoy.cli.io._project import DECOY_DIR_GITIGNORE
from decoy.cli.project._new import create_project

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"
RUN_A = "20261105T101010000001Z-aaaaaaaa"
RUN_B = "20261106T101010000001Z-bbbbbbbb"
RUN_C = "20261107T101010000001Z-cccccccc"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return folder


def _project(parent: Path, name: str, members: tuple[str, ...] = ()) -> Path:
    root = parent / name
    root.mkdir(parents=True)
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    for member in members:
        folder = root / "pipelines" / member
        folder.mkdir(parents=True)
        (folder / "pipeline.yaml").write_text("name: x\n", encoding="utf-8")
    return root


def _runs(root: Path, name: str, *ids: str, latest: str | None = None) -> None:
    folder = root / "out" / name
    for run_id in ids:
        (folder / run_id).mkdir(parents=True)
    if latest is not None:
        (folder / "LATEST").write_text(latest, encoding="utf-8")


def _json(res) -> dict:
    return json.loads(res.stdout)


# --- AT-24: project new -----------------------------------------------------------------------


def test_new_writes_the_four_entries(tmp_path: Path) -> None:
    target = tmp_path / "work" / "acme"

    res = runner.invoke(app, ["project", "new", str(target)])

    assert res.exit_code == EXIT_OK, res.output
    assert (target / "decoy.yaml").read_text(encoding="utf-8") == MARKER
    assert (target / "pipelines").is_dir()
    assert (target / "out" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert (target / DECOY_DIR / ".gitignore").read_text(encoding="utf-8") == DECOY_DIR_GITIGNORE
    assert find_project(None, target).root == target.resolve()
    assert "decoy init" in res.output


def test_new_dot_uses_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)

    res = runner.invoke(app, ["project", "new", "."])

    assert res.exit_code == EXIT_OK, res.output
    assert (here / "decoy.yaml").is_file()


def test_second_call_fills_only_what_is_missing(tmp_path: Path) -> None:
    target = tmp_path / "acme"
    assert runner.invoke(app, ["project", "new", str(target)]).exit_code == EXIT_OK
    (target / "pipelines").rmdir()
    (target / "out" / ".gitignore").write_text("custom\n", encoding="utf-8")
    marker_before = (target / "decoy.yaml").stat().st_mtime_ns

    res = runner.invoke(app, ["project", "new", str(target)])

    assert res.exit_code == EXIT_OK, res.output
    assert "already a project" in res.output
    assert (target / "pipelines").is_dir()
    assert (target / "out" / ".gitignore").read_text(encoding="utf-8") == "custom\n"
    assert (target / "decoy.yaml").stat().st_mtime_ns == marker_before


def test_concurrent_creates_leave_one_valid_marker(tmp_path: Path) -> None:
    target = tmp_path / "race"
    gate = threading.Barrier(8)
    failures: list[BaseException] = []

    def work() -> None:
        gate.wait()
        try:
            create_project(target)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert (target / "decoy.yaml").read_text(encoding="utf-8") == MARKER
    assert find_project(None, target).root == target.resolve()


def test_new_refuses_an_invalid_marker(tmp_path: Path) -> None:
    target = tmp_path / "bad"
    target.mkdir()
    (target / "decoy.yaml").write_text("kind: something-else\n", encoding="utf-8")

    res = runner.invoke(app, ["project", "new", str(target), "--json"])

    assert res.exit_code == EXIT_USAGE
    body = _json(res)
    assert body["status"] == "error"
    assert body["code"] == "layout.project_marker_invalid"
    assert not (target / "pipelines").exists()
    assert (target / "decoy.yaml").read_text(encoding="utf-8") == "kind: something-else\n"


def test_new_refuses_a_pipeline_file_named_decoy_yaml(tmp_path: Path) -> None:
    target = tmp_path / "pipe"
    target.mkdir()
    (target / "decoy.yaml").write_text("name: members\n", encoding="utf-8")

    res = runner.invoke(app, ["project", "new", str(target), "--json"])

    assert res.exit_code == EXIT_USAGE
    assert _json(res)["code"] == "layout.project_marker_invalid"


@pytest.mark.parametrize("which", ["home", "parent", "slash"])
def test_new_refuses_home_its_parents_and_slash(home: Path, which: str) -> None:
    folder = {"home": home, "parent": home.parent, "slash": Path(os.sep)}[which]
    before = sorted(p.name for p in folder.iterdir())

    res = runner.invoke(app, ["project", "new", str(folder), "--json"])

    assert res.exit_code == EXIT_USAGE
    assert _json(res)["code"] == "layout.project_root_refused"
    assert sorted(p.name for p in folder.iterdir()) == before


def test_new_inside_a_project_warns_and_still_makes_one(tmp_path: Path) -> None:
    outer = _project(tmp_path, "outer")
    inner = outer / "client"

    res = runner.invoke(app, ["project", "new", str(inner), "--json"])

    assert res.exit_code == EXIT_OK, res.output
    codes = [w["code"] for w in _json(res)["warnings"]]
    assert codes == ["layout.project_nested"]
    assert find_project(None, inner).root == inner.resolve()
    assert find_project(inner, None).root == inner.resolve()


def test_new_json_reports_the_root_and_what_it_made(tmp_path: Path) -> None:
    target = tmp_path / "acme"

    body = _json(runner.invoke(app, ["project", "new", str(target), "--json"]))

    assert body["command"] == "project new"
    assert body["status"] == "ok"
    assert body["root"] == str(target.resolve())
    assert body["already_project"] is False
    assert body["warnings"] == []


def test_new_onto_a_file_exits_1_without_a_traceback(tmp_path: Path) -> None:
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")

    res = runner.invoke(app, ["project", "new", str(target), "--json"])

    assert res.exit_code == EXIT_USAGE
    assert _json(res)["status"] == "error"


# --- AT-25: project show and list -------------------------------------------------------------


def test_show_lists_only_valid_members_with_runs_from_the_folders(tmp_path: Path) -> None:
    root = _project(tmp_path, "acme", ("beta", "alpha"))
    (root / "pipelines" / "empty").mkdir()
    (root / "pipelines" / "bad name").mkdir()
    (root / "pipelines" / "bad name" / "pipeline.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "free.yaml").write_text("name: free\n", encoding="utf-8")
    (root / "out" / "free").mkdir(parents=True)
    (root / "out" / "free" / "PIPELINE").write_text("free.yaml\n", encoding="utf-8")
    _runs(root, "alpha", RUN_A, RUN_B, RUN_C, "junk", latest=RUN_B + "\n")

    res = runner.invoke(app, ["--project", str(root), "project", "show", "--json"])

    assert res.exit_code == EXIT_OK, res.output
    body = _json(res)
    assert body["command"] == "project show"
    assert body["root"] == str(root.resolve())
    rows = {p["name"]: p for p in body["pipelines"]}
    assert list(rows) == ["alpha", "beta"]
    assert rows["alpha"] == {
        "name": "alpha",
        "yaml": "pipelines/alpha/pipeline.yaml",
        "last_run": RUN_C,
        "last_clean_run": RUN_B,
        "status": "-",
    }
    assert rows["beta"]["last_run"] is None
    assert rows["beta"]["last_clean_run"] is None
    assert body["warnings"] == []


def test_show_ignores_a_malformed_latest_with_a_warning(tmp_path: Path) -> None:
    root = _project(tmp_path, "acme", ("alpha",))
    _runs(root, "alpha", RUN_A, latest="../../etc\n")

    body = _json(runner.invoke(app, ["--project", str(root), "project", "show", "--json"]))

    row = body["pipelines"][0]
    assert row["last_run"] == RUN_A
    assert row["last_clean_run"] is None
    assert [w["code"] for w in body["warnings"]] == ["layout.latest_invalid"]


def test_show_ignores_a_latest_that_names_no_folder(tmp_path: Path) -> None:
    root = _project(tmp_path, "acme", ("alpha",))
    _runs(root, "alpha", RUN_A, latest=RUN_C + "\n")

    body = _json(runner.invoke(app, ["--project", str(root), "project", "show", "--json"]))

    assert body["pipelines"][0]["last_clean_run"] is None
    assert [w["code"] for w in body["warnings"]] == ["layout.latest_invalid"]


def test_show_walks_up_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, "acme", ("alpha",))
    monkeypatch.chdir(root / "pipelines" / "alpha")

    res = runner.invoke(app, ["project", "show"])

    assert res.exit_code == EXIT_OK, res.output
    assert "alpha" in res.output
    assert str(root.resolve()) in res.output.replace("\n", "")


def test_show_outside_a_project_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = tmp_path / "plain"
    here.mkdir()
    monkeypatch.chdir(here)

    res = runner.invoke(app, ["project", "show", "--json"])

    assert res.exit_code == EXIT_USAGE
    assert _json(res)["code"] == "layout.project_not_found"


def test_show_with_no_members_says_so(tmp_path: Path) -> None:
    root = _project(tmp_path, "acme")

    res = runner.invoke(app, ["--project", str(root), "project", "show"])

    assert res.exit_code == EXIT_OK, res.output
    assert "no pipelines" in res.output.lower()


def test_list_finds_projects_one_level_down(tmp_path: Path) -> None:
    base = tmp_path / "clients"
    base.mkdir()
    _project(base, "zed", ("a", "b"))
    _project(base, "acme", ("a",))
    (base / "plain").mkdir()
    deep = base / "plain" / "inner"
    deep.mkdir()
    (deep / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    (base / "invalid").mkdir()
    (base / "invalid" / "decoy.yaml").write_text("kind: nope\n", encoding="utf-8")

    res = runner.invoke(app, ["project", "list", str(base), "--json"])

    assert res.exit_code == EXIT_OK, res.output
    body = _json(res)
    assert body["command"] == "project list"
    assert [(p["folder"], p["pipelines"]) for p in body["projects"]] == [("acme", 1), ("zed", 2)]
    assert body["projects"][0]["root"] == str((base / "acme").resolve())
    assert [w["code"] for w in body["warnings"]] == ["layout.project_marker_invalid"]


def test_list_includes_the_folder_itself_when_it_is_a_project(tmp_path: Path) -> None:
    root = _project(tmp_path, "acme", ("a",))
    _project(root, "sub")

    body = _json(runner.invoke(app, ["project", "list", str(root), "--json"]))

    assert [(p["folder"], p["pipelines"]) for p in body["projects"]] == [(".", 1), ("sub", 0)]


def test_list_defaults_to_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "clients"
    _project(base, "acme")
    monkeypatch.chdir(base)

    res = runner.invoke(app, ["project", "list"])

    assert res.exit_code == EXIT_OK, res.output
    assert "acme" in res.output


def test_list_with_nothing_found_says_so(tmp_path: Path) -> None:
    res = runner.invoke(app, ["project", "list", str(tmp_path)])

    assert res.exit_code == EXIT_OK, res.output
    assert "no projects" in res.output.lower()


def test_list_does_not_follow_a_linked_folder(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("links need POSIX here")
    base = tmp_path / "clients"
    base.mkdir()
    real = _project(tmp_path, "elsewhere")
    (base / "link").symlink_to(real, target_is_directory=True)

    body = _json(runner.invoke(app, ["project", "list", str(base), "--json"]))

    assert body["projects"] == []


def test_project_commands_are_registered_in_help() -> None:
    res = runner.invoke(app, ["project", "--help"], terminal_width=120)

    assert res.exit_code == EXIT_OK
    for word in ("new", "show", "list"):
        assert word in res.output
