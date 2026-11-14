"""AT-21 and AT-22 (P8): `run` with no argument picks the project's only pipeline, `run --all`
runs every pipeline in its own process.

`--all` starts one child per pipeline (`python -c <entry point> --project ROOT run YAML --json ...`), so
engine state, logging and memory limits never carry from one pipeline to the next, and each
child's exit code keeps its single-run meaning. A process spy sits on `subprocess.run`: it
records every child command line and either lets the child really run or answers with a made-up
exit code and output, so the summary rules are tested without paying for a process per cell.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import csv_source

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"
REAL_RUN = subprocess.run
# The summary exit code is the first of these that any child produced.
PRIORITY = (3, 5, 1, 4, 2, 0)
MASTER_KEY = "ab" * 32
FAN_OUT = Path(__file__).resolve().parents[3] / "src" / "decoy" / "cli" / "project" / "_run_all.py"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    monkeypatch.delenv("DECOY_MASTER_KEY", raising=False)
    return folder


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    return root


def _pipeline(root: Path, name: str, *, broken: bool = False) -> Path:
    src = root / "data" / f"{name}.csv"
    src.parent.mkdir(exist_ok=True)
    emails = pd.Series(["a@example.com", "b@example.com"], dtype="string")
    pd.DataFrame({"email": emails}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    if broken:
        cfg["tables"][0]["columns"][0]["strategy"] = "no_such_strategy"
    path = root / "pipelines" / name / "pipeline.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _fake_project(tmp_path: Path, names: list[str]) -> Path:
    root = _project(tmp_path)
    for name in names:
        _pipeline(root, name)
    return root


def _runs(root: Path, name: str) -> list[Path]:
    folder = root / "out" / name
    return (
        sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink())
        if folder.is_dir()
        else []
    )


class Spy:
    """Records each child process; `answers` maps a pipeline name to (exit code, stdout)."""

    def __init__(self, answers: dict[str, tuple[int, str]] | None = None) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []
        self.envs: list[object] = []
        self.codes: list[int] = []

    def __call__(self, cmd: list[str], *args: object, **kwargs: object):
        self.calls.append([str(part) for part in cmd])
        self.envs.append(kwargs.get("env"))
        if self.answers is None:
            done = REAL_RUN(cmd, *args, **kwargs)  # type: ignore[call-overload]
        else:
            name = Path(str(cmd[cmd.index("run") + 1])).parent.name
            code, out = self.answers[name]
            done = subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")
        self.codes.append(done.returncode)
        return done


def _spy(monkeypatch: pytest.MonkeyPatch, answers: dict[str, tuple[int, str]] | None = None) -> Spy:
    spy = Spy(answers)
    monkeypatch.setattr(subprocess, "run", spy)
    return spy


def _ok(name: str, folder: str | None = None) -> str:
    payload: dict = {"command": "run", "status": "ok", "pipeline": {"name": name}}
    if folder is not None:
        payload["output_dir"] = folder
    return json.dumps(payload)


def _run_all(root: Path, *args: str):
    return runner.invoke(app, ["--project", str(root), "run", "--all", *args])


def _flat(text: str) -> str:
    return " ".join(text.split())


# --- AT-21: no argument ---------------------------------------------------------------------


def test_no_argument_runs_the_only_pipeline(tmp_path: Path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["orders"])
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0, result.output
    assert "Running the only pipeline: orders" in _flat(result.output)
    assert len(_runs(root, "orders")) == 1


def test_no_argument_with_json_keeps_stdout_one_document(tmp_path: Path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["orders"])
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["pipeline"]["name"] == "orders"
    assert payload["pipeline"]["given_as"] == "name"


def test_no_argument_with_no_pipeline_exits_1_with_the_init_hint(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert "decoy init" in _flat(result.output)


def test_no_argument_with_two_pipelines_lists_both_and_exits_1(tmp_path: Path, monkeypatch):
    root = _fake_project(tmp_path, ["orders", "claims"])
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    text = _flat(result.output)
    assert "claims" in text and "orders" in text
    assert _runs(root, "orders") == [] and _runs(root, "claims") == []


def test_no_argument_two_pipelines_json_names_them_in_the_envelope(tmp_path: Path, monkeypatch):
    root = _fake_project(tmp_path, ["orders", "claims"])
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["run", "--json"])
    assert result.exit_code == 1
    body = json.loads(result.stdout)
    assert body["status"] == "error" and body["command"] == "run"
    assert "claims" in body["error"] and "orders" in body["error"]


def test_no_argument_outside_a_project_is_the_usage_error_with_the_hint(tmp_path, monkeypatch):
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2
    text = _flat(result.output)
    assert "Missing" in text
    assert "--project" in text


def test_no_argument_uses_the_project_flag_and_the_environment(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["orders"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    by_flag = runner.invoke(app, ["--project", str(root), "run"])
    assert by_flag.exit_code == 0, by_flag.output
    monkeypatch.setenv("DECOY_PROJECT", str(root))
    by_env = runner.invoke(app, ["run"])
    assert by_env.exit_code == 0, by_env.output
    assert len(_runs(root, "orders")) == 2


# --- AT-22: --all ---------------------------------------------------------------------------


def test_all_runs_each_pipeline_in_its_own_process_in_name_order(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["gamma", "alpha", "beta"])
    spy = _spy(monkeypatch)
    result = _run_all(root)
    assert result.exit_code == 0, result.output
    assert len(spy.calls) == 3
    yamls = [Path(call[call.index("run") + 1]) for call in spy.calls]
    assert [y.parent.name for y in yamls] == ["alpha", "beta", "gamma"]
    for call in spy.calls:
        assert call[0] == sys.executable and call[1] == "-c" and "decoy.__main__" in call[2]
        assert "-m" not in call[:3]
        assert call[call.index("--project") + 1] == str(root)
        assert call.index("--project") < call.index("run")
        assert "--json" in call
        assert "--all" not in call
    for name in ("alpha", "beta", "gamma"):
        assert len(_runs(root, name)) == 1
    assert "All 3 pipelines exited 0." in _flat(result.output)


def test_a_failing_middle_pipeline_does_not_stop_the_third(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    _pipeline(root, "alpha")
    _pipeline(root, "beta", broken=True)
    _pipeline(root, "gamma")
    spy = _spy(monkeypatch)
    result = _run_all(root, "--json")
    assert len(spy.calls) == 3
    assert spy.codes[0] == 0 and spy.codes[1] != 0 and spy.codes[2] == 0
    assert len(_runs(root, "gamma")) == 1
    body = json.loads(result.stdout)
    assert [p["exit_code"] for p in body["pipelines"]] == spy.codes
    assert result.exit_code == body["exit_code"] == spy.codes[1]


@pytest.mark.parametrize(
    ("first", "second"), list(itertools.product(range(6), range(6))), ids=lambda c: str(c)
)
def test_the_exit_code_follows_the_priority_order_for_each_pair(
    tmp_path, monkeypatch, first: int, second: int
) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    _spy(monkeypatch, {"alpha": (first, _ok("alpha")), "beta": (second, _ok("beta"))})
    result = _run_all(root)
    expected = next(code for code in PRIORITY if code in (first, second))
    assert result.exit_code == expected, result.output


@pytest.mark.parametrize(
    ("code", "out"),
    [
        pytest.param(-9, _ok("alpha"), id="killed-by-a-signal"),
        pytest.param(-11, "", id="killed-no-output"),
        pytest.param(9, _ok("alpha"), id="exit-code-outside-0-to-5"),
        pytest.param(6, _ok("alpha"), id="partial-code-is-not-a-run-code"),
        pytest.param(0, "{not json", id="broken-json"),
        pytest.param(0, "", id="empty-output"),
        pytest.param(0, "[1, 2]", id="json-that-is-not-an-object"),
    ],
)
def test_a_child_that_cannot_be_trusted_makes_the_summary_exit_3(
    tmp_path, monkeypatch, code: int, out: str
) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    _spy(monkeypatch, {"alpha": (code, out), "beta": (0, _ok("beta"))})
    result = _run_all(root)
    assert result.exit_code == 3, result.output


def test_a_broken_child_is_never_hidden_by_a_clean_one(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    _spy(monkeypatch, {"alpha": (0, _ok("alpha")), "beta": (0, "oops")})
    assert _run_all(root).exit_code == 3


def test_all_json_lists_every_child_payload_and_the_exit_code(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    _spy(monkeypatch, {"alpha": (0, _ok("alpha", "/x/a")), "beta": (4, _ok("beta", "/x/b"))})
    result = _run_all(root, "--json")
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["exit_code"] == 4
    assert [p["pipeline"]["name"] for p in body["pipelines"]] == ["alpha", "beta"]
    assert [p["exit_code"] for p in body["pipelines"]] == [0, 4]
    assert body["pipelines"][1]["output_dir"] == "/x/b"


def test_all_json_gives_a_broken_child_a_record_with_its_name_and_code(
    tmp_path, monkeypatch
) -> None:
    root = _fake_project(tmp_path, ["alpha"])
    _spy(monkeypatch, {"alpha": (-9, "")})
    result = _run_all(root, "--json")
    body = json.loads(result.stdout)
    assert result.exit_code == body["exit_code"] == 3
    assert len(body["pipelines"]) == 1
    record = body["pipelines"][0]
    assert record["status"] == "failed" and record["name"] == "alpha" and record["exit_code"] == 3


def test_the_table_names_each_pipeline_its_code_and_run_folder(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    _spy(monkeypatch, {"alpha": (0, _ok("alpha", "/x/a")), "beta": (4, _ok("beta", "/x/b"))})
    text = _flat(_run_all(root).output)
    assert "alpha" in text and "/x/a" in text
    assert "beta" in text and "/x/b" in text
    assert "1 of 2 pipelines exited non-zero" in text


@pytest.mark.parametrize(
    "flag", [["--evidence-out", "e.json"], ["--vault", "v.bin"], ["--out-dir", "o"]]
)
def test_a_flag_that_names_one_file_is_refused_with_all(tmp_path, monkeypatch, flag) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    spy = _spy(monkeypatch)
    result = _run_all(root, *flag)
    assert result.exit_code == 1
    assert flag[0] in _flat(result.output)
    assert spy.calls == []


def test_a_name_with_all_is_refused(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    spy = _spy(monkeypatch)
    result = runner.invoke(app, ["--project", str(root), "run", "alpha", "--all"])
    assert result.exit_code == 1
    assert spy.calls == []
    assert _runs(root, "alpha") == []


def test_a_path_with_all_is_refused(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha"])
    spy = _spy(monkeypatch)
    result = runner.invoke(app, ["run", str(root / "pipelines/alpha/pipeline.yaml"), "--all"])
    assert result.exit_code == 1
    assert spy.calls == []


def test_all_with_no_pipelines_exits_1_with_the_init_hint(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    spy = _spy(monkeypatch)
    result = _run_all(root)
    assert result.exit_code == 1
    assert "decoy init" in _flat(result.output)
    assert spy.calls == []


def test_all_outside_a_project_is_refused(tmp_path, monkeypatch) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    spy = _spy(monkeypatch)
    result = runner.invoke(app, ["run", "--all"])
    assert result.exit_code == 1
    assert "layout.project_not_found" in _flat(result.output)
    assert spy.calls == []


def test_flags_are_forwarded_to_each_child(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    spy = _spy(monkeypatch, {"alpha": (0, _ok("alpha")), "beta": (0, _ok("beta"))})
    result = _run_all(root, "--chunked", "--chunk-size", "50", "--no-native", "--fidelity")
    assert result.exit_code == 0, result.output
    for call in spy.calls:
        assert "--chunked" in call and "--no-native" in call and "--fidelity" in call
        assert call[call.index("--chunk-size") + 1] == "50"


def test_a_master_key_reaches_children_by_environment_not_by_command_line(
    tmp_path, monkeypatch
) -> None:
    root = _fake_project(tmp_path, ["alpha"])
    spy = _spy(monkeypatch, {"alpha": (0, _ok("alpha"))})
    result = _run_all(root, "--master-key", MASTER_KEY, "--key-label", "demo")
    assert result.exit_code == 0, result.output
    assert all(MASTER_KEY not in part for part in spy.calls[0])
    env = spy.envs[0]
    assert isinstance(env, dict) and env.get("DECOY_MASTER_KEY") == MASTER_KEY
    assert "--key-label" in spy.calls[0]


def test_json_stdout_is_one_document_even_with_child_output(tmp_path, monkeypatch) -> None:
    root = _fake_project(tmp_path, ["alpha"])
    _spy(monkeypatch)
    result = _run_all(root, "--json")
    assert result.exit_code == 0, result.output
    json.loads(result.stdout)


def test_the_fan_out_lives_in_the_project_package_and_spawns_processes() -> None:
    text = FAN_OUT.read_text(encoding="utf-8")
    assert "decoy.cli.run" not in text
    assert "subprocess.run" in text


@pytest.mark.parametrize("shadow", ["decoy.py", "decoy/__init__.py", "typer.py"])
def test_a_file_in_the_project_never_replaces_the_installed_cli(
    tmp_path, monkeypatch, shadow: str
) -> None:
    root = _fake_project(tmp_path, ["alpha", "beta"])
    marker = tmp_path / "shadow-ran"
    target = root / shadow
    target.parent.mkdir(exist_ok=True)
    target.write_text(f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in sys.path if p and p != str(root)))
    spy = _spy(monkeypatch)
    result = runner.invoke(app, ["run", "--all"])
    assert not marker.exists()
    assert result.exit_code == 0, result.output
    assert len(spy.calls) == 2
    assert all(len(_runs(root, name)) == 1 for name in ("alpha", "beta"))
