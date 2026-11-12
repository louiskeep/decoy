"""AT-18, AT-19, AT-20 and AT-23 (P5): a pipeline is given by path or by name on every command.

Twelve parameters take a pipeline YAML. A token that is an existing file, or looks like a path
(a separator, or `.yaml`/`.yml`), is a path and keeps today's Click behaviour (exit 2). Any other
token is a name looked up under `<project>/pipelines/<name>/pipeline.yaml`, and a refusal there
exits 1 with a `layout.*` code inside the command's own `--json` envelope. `--project DIR` and
`DECOY_PROJECT` pick the project for a name; `--project` also checks a path.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import find_project, list_pipelines
from tests.csv_sources import csv_source

runner = CliRunner()
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")
MARKER = "kind: decoy-project/v1\n"
USAGE_ERROR = 2
_RUN_ID = re.compile(r"\d{8}T\d{12}Z-[0-9a-f]+")
_VOLATILE = re.compile(r"time|duration|elapsed|started|finished|_at$|_ms$|seconds|invocation|rss")


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `$HOME` beside the trees under test, and no ambient project variable."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return folder


def _project(tmp_path: Path, name: str = "proj") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    return root


def _config(root: Path, tag: str, **extra: object) -> dict:
    src = root / "data" / f"{tag}.csv"
    src.parent.mkdir(exist_ok=True)
    emails = pd.Series(["a@example.com", "b@example.com"], dtype="string")
    pd.DataFrame({"email": emails}).to_csv(src, index=False)
    return {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
        **extra,
    }


def _pipeline(root: Path, name: str = "orders", **extra: object) -> Path:
    path = root / "pipelines" / name / "pipeline.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_config(root, name, **extra)), encoding="utf-8")
    return path


def _subset_pipeline(root: Path, name: str = "slice") -> Path:
    customers, orders = root / "data" / "c.parquet", root / "data" / "o.parquet"
    customers.parent.mkdir(exist_ok=True)
    pl.DataFrame({"id": list(range(1, 21))}).write_parquet(customers)
    fk = [(i % 20) + 1 for i in range(40)]
    pl.DataFrame({"id": list(range(1, 41)), "customer_id": fk}).write_parquet(orders)
    hashed = {"strategy": "hash", "namespace": "n"}
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {
            "customers": {"type": "file", "format": "parquet", "path": str(customers)},
            "orders": {"type": "file", "format": "parquet", "path": str(orders)},
        },
        "tables": [
            {"name": "customers", "columns": [{"name": "id", **hashed}]},
            {"name": "orders", "columns": [{"name": "customer_id", **hashed}]},
        ],
        "relationships": [
            {
                "parent": {"table": "customers", "columns": ["id"]},
                "children": [{"table": "orders", "columns": ["customer_id"]}],
                "orphan_policy": "preserve",
                "namespace": "n",
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "parquet", "path": "c_out.parquet"},
            "orders": {"type": "file", "format": "parquet", "path": "o_out.parquet"},
        },
        "subset": {
            "seeds": [
                {"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 0.25}
            ]
        },
    }
    path = root / "pipelines" / name / "pipeline.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _invoke(*argv: str, env: dict[str, str] | None = None):
    return runner.invoke(app, list(argv), env=env, color=False)


def _body(result) -> dict:
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"_unparsed": result.output}


# --- AT-18: every command, name beside path ----------------------------------------------


@dataclass(frozen=True)
class Cmd:
    label: str
    command: str  # the `command` member of the command's own envelope
    argv: Callable[[str, dict[str, str]], list[str]]
    pipeline: str = "orders"
    full_success: bool = True


COMMANDS = [
    Cmd("run", "run", lambda t, a: ["run", t, "--json"]),
    Cmd("validate", "validate", lambda t, a: ["validate", t, "--json"]),
    Cmd("validate config", "validate", lambda t, a: ["validate", "config", t, "--json"]),
    Cmd("validate compile", "validate compile", lambda t, a: ["validate", "compile", t, "--json"]),
    Cmd(
        "validate preflight",
        "validate preflight",
        lambda t, a: ["validate", "preflight", t, "--json"],
    ),
    Cmd("subset", "subset", lambda t, a: ["subset", t, "--dry-run", "--json"], "slice"),
    Cmd(
        "tokenize",
        "tokenize",
        lambda t, a: ["tokenize", t, "--vault", a["new_vault"], "--json"],
        full_success=False,
    ),
    Cmd(
        "detokenize",
        "detokenize",
        lambda t, a: ["detokenize", t, a["csv"], "--vault", a["vault"], "--json"],
        full_success=False,
    ),
    Cmd("unmask", "unmask", lambda t, a: ["unmask", t, a["csv"], "--json"], full_success=False),
    Cmd(
        "report fidelity",
        "report fidelity",
        lambda t, a: ["report", "fidelity", a["csv"], a["csv"], "--config", t, "--json"],
    ),
    Cmd(
        "report integrity",
        "report integrity",
        lambda t, a: [
            *("report", "integrity", a["csv"], "--source", a["csv"]),
            *("--config", t, "--json"),
        ],
        full_success=False,
    ),
    Cmd(
        "report vault",
        "report vault",
        lambda t, a: ["report", "vault", a["vault"], "--config", t, "--json"],
        full_success=False,
    ),
]
IDS = [c.label for c in COMMANDS]


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = _project(tmp_path)
    _pipeline(root)
    _subset_pipeline(root)
    (root / "sub").mkdir()
    aux = {
        "csv": str(root / "data" / "orders.csv"),
        "vault": str(root / "data" / "existing.vault"),
        "new_vault": str(root / "data" / "new.vault"),
    }
    Path(aux["vault"]).write_bytes(b"")
    return root, aux


def _normal(result, *spellings: str) -> dict:
    text = json.dumps(_body(result), sort_keys=True)
    for spelling in spellings:
        text = text.replace(json.dumps(spelling)[1:-1], "<CFG>")
    text = _RUN_ID.sub("<RUN>", text)

    def scrub(node):
        if isinstance(node, dict):
            return {
                k: scrub(v) for k, v in node.items() if not _VOLATILE.search(k) and k != "given_as"
            }
        if isinstance(node, list):
            return [scrub(v) for v in node]
        return node

    return scrub(json.loads(text))


@pytest.mark.parametrize("cmd", COMMANDS, ids=IDS)
def test_a_name_from_a_subfolder_gives_the_result_of_the_path_from_the_root(
    cmd: Cmd, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, aux = world
    path = str(root / "pipelines" / cmd.pipeline / "pipeline.yaml")
    monkeypatch.chdir(root)
    Path(aux["new_vault"]).unlink(missing_ok=True)
    by_path = _invoke(*cmd.argv(path, aux))
    monkeypatch.chdir(root / "sub")
    Path(aux["new_vault"]).unlink(missing_ok=True)
    by_name = _invoke(*cmd.argv(cmd.pipeline, aux))
    assert by_name.exit_code == by_path.exit_code, by_name.output
    assert by_name.exit_code != USAGE_ERROR, by_name.output
    if cmd.full_success:
        assert by_name.exit_code == EXIT_OK, by_name.output
    assert "layout." not in json.dumps(_body(by_name))
    assert _normal(by_name, cmd.pipeline, path) == _normal(by_path, cmd.pipeline, path)


@pytest.mark.parametrize("cmd", COMMANDS, ids=IDS)
def test_an_unknown_name_is_a_layout_refusal_in_the_command_envelope(
    cmd: Cmd, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, aux = world
    monkeypatch.chdir(root / "sub")
    result = _invoke(*cmd.argv("nope", aux))
    assert result.exit_code == EXIT_USAGE, result.output
    doc = _body(result)
    assert (doc["command"], doc["status"], doc["code"]) == (
        cmd.command,
        "error",
        "layout.pipeline_unknown",
    )
    assert doc["config"] == "nope"
    assert "orders" in doc["error"]


def test_explain_modes_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _invoke("explain", "modes").exit_code == EXIT_OK


@pytest.mark.parametrize("cmd", COMMANDS[:2], ids=IDS[:2])
def test_a_refusal_prints_one_error_line_and_quiet_prints_nothing(
    cmd: Cmd, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, aux = world
    monkeypatch.chdir(root)
    argv = [a for a in cmd.argv("nope", aux) if a != "--json"]
    plain = runner.invoke(app, argv)
    assert plain.exit_code == EXIT_USAGE
    assert plain.output.startswith("error: ") and "layout." not in plain.stdout
    quiet = runner.invoke(app, [*argv, "--quiet"])
    assert quiet.exit_code == EXIT_USAGE
    assert quiet.output == ""


# --- AT-19: token rules ------------------------------------------------------------------


def test_an_existing_extensionless_file_named_like_a_pipeline_is_a_path(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = world
    (root / "orders").write_text((root / "pipelines/orders/pipeline.yaml").read_text(), "utf-8")
    monkeypatch.chdir(root)
    result = _invoke("run", "orders", "--json")
    assert result.exit_code == EXIT_OK, result.output
    assert _body(result)["pipeline"]["given_as"] == "path"


def test_a_name_is_reported_as_given_by_name(world, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = world
    monkeypatch.chdir(root)
    by_name = _body(_invoke("run", "orders", "--json"))
    by_path = _body(_invoke("run", "pipelines/orders/pipeline.yaml", "--json"))
    assert by_name["pipeline"]["given_as"] == "name"
    assert by_path["pipeline"]["given_as"] == "path"
    assert by_name["pipeline"]["yaml"] == by_path["pipeline"]["yaml"]


@pytest.mark.parametrize("token", ["./missing.yaml", "x/y", "missing.yml", "-", "a\\b"])
def test_a_path_shaped_token_that_does_not_exist_stays_a_usage_error(
    token: str, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, aux = world
    monkeypatch.chdir(root)
    for argv in (
        ["run", token],
        ["validate", "config", token],
        ["report", "vault", aux["csv"], "--config", token],
    ):
        result = _invoke(*argv)
        assert result.exit_code == USAGE_ERROR, result.output
        assert "layout." not in result.output


def test_a_folder_beside_the_project_is_a_path_and_never_a_name(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = world
    (root / "x").mkdir()
    monkeypatch.chdir(root / "sub")
    result = _invoke("run", "../x", "--json")
    assert result.exit_code == USAGE_ERROR, result.output
    assert "layout." not in result.output
    assert not (root / "out").exists()


@pytest.mark.parametrize("token", ["a b", "..", ".hidden", "CON", "x" * 65])
def test_a_token_that_fails_the_name_rule_is_refused(
    token: str, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = world
    # `..` would reach this file if the name were joined under pipelines/ unchecked.
    text = (root / "pipelines/orders/pipeline.yaml").read_text()
    (root / "pipeline.yaml").write_text(text, "utf-8")
    monkeypatch.chdir(root)
    result = _invoke("run", token, "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert _body(result)["code"] == "layout.pipeline_name_invalid"
    assert not (root / "out").exists()


def test_an_unknown_name_lists_every_name_and_the_close_match(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = world
    _pipeline(root, "members")
    monkeypatch.chdir(root)
    doc = _body(_invoke("validate", "ordres", "--json"))
    assert doc["code"] == "layout.pipeline_unknown"
    assert "Known pipelines: members, orders, slice." in doc["error"]
    assert "Did you mean orders?" in doc["error"]


def test_a_name_with_no_project_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    result = _invoke("validate", "orders", "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert _body(result)["code"] == "layout.project_not_found"


@posix_only
def test_a_symlink_that_leaves_pipelines_is_unknown_and_unlisted(
    world, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = world
    text = (root / "pipelines/orders/pipeline.yaml").read_text()
    elsewhere = tmp_path / "elsewhere-target"
    elsewhere.mkdir()
    (elsewhere / "pipeline.yaml").write_text(text, "utf-8")
    (root / "pipelines" / "evil").symlink_to(elsewhere, target_is_directory=True)
    (tmp_path / "x.yaml").write_text(text, "utf-8")
    (root / "pipelines" / "ok").mkdir()
    (root / "pipelines" / "ok" / "pipeline.yaml").symlink_to("../../../x.yaml")
    monkeypatch.chdir(root)
    for name in ("evil", "ok"):
        result = _invoke("run", name, "--json")
        assert result.exit_code == EXIT_USAGE, result.output
        assert _body(result)["code"] == "layout.pipeline_unknown"
        assert "elsewhere-target" not in result.output and "x.yaml" not in result.output
    assert [e.name for e in list_pipelines(find_project(root, None))] == ["orders", "slice"]
    assert not (root / "out").exists()


# --- AT-20: the name rule ----------------------------------------------------------------


def test_a_declared_name_that_differs_from_the_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _pipeline(root, name="sales")
    monkeypatch.chdir(root)
    result = _invoke("run", "orders", "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.pipeline_name_mismatch" in result.output


@pytest.mark.parametrize("declared", [{"name": "orders"}, {}])
def test_a_matching_or_absent_name_runs_into_the_name_folder(
    declared: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _pipeline(root, **declared)
    monkeypatch.chdir(root)
    result = _invoke("run", "orders", "--json")
    assert result.exit_code == EXIT_OK, result.output
    (run,) = (root / "out" / "orders").glob("[0-9]*")
    assert (run / "masked.csv").is_file()


# --- AT-23: project selection ------------------------------------------------------------


@pytest.fixture
def three(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Three projects with one pipeline name each, and a folder in none of them."""
    a, b, c = (_project(tmp_path, f"p{n}") for n in "abc")
    for root in (a, b, c):
        _pipeline(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    return a, b, c, outside


def _root_of(result) -> Path:
    assert result.exit_code == EXIT_OK, result.output
    return Path(_body(result)["project"]["root"])


def test_project_flag_and_variable_resolve_a_name_from_outside(three, monkeypatch) -> None:
    _, b, c, outside = three
    monkeypatch.chdir(outside)
    assert _root_of(_invoke("--project", str(c), "run", "orders", "--json")) == c.resolve()
    env = {"DECOY_PROJECT": str(b)}
    assert _root_of(_invoke("run", "orders", "--json", env=env)) == b.resolve()


def test_flag_beats_variable_and_variable_beats_the_walk(three, monkeypatch) -> None:
    a, b, c, _ = three
    monkeypatch.chdir(a / "pipelines")
    env = {"DECOY_PROJECT": str(b)}
    assert _root_of(_invoke("run", "orders", "--json")) == a.resolve()
    assert _root_of(_invoke("run", "orders", "--json", env=env)) == b.resolve()
    assert _root_of(_invoke("--project", str(c), "run", "orders", "--json", env=env)) == c.resolve()


def test_an_empty_variable_counts_as_unset(three, monkeypatch) -> None:
    a, *_ = three
    monkeypatch.chdir(a)
    assert _root_of(_invoke("run", "orders", "--json", env={"DECOY_PROJECT": ""})) == a.resolve()


def test_project_flag_beside_a_path_from_another_project_is_a_mismatch(three, monkeypatch) -> None:
    a, _, c, outside = three
    monkeypatch.chdir(outside)
    path = str(a / "pipelines" / "orders" / "pipeline.yaml")
    result = _invoke("--project", str(c), "run", path, "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert _body(result)["code"] == "layout.project_mismatch"
    assert not (a / "out").exists() and not (c / "out").exists()


def test_project_flag_beside_a_path_in_the_same_project_runs(three, monkeypatch) -> None:
    a, _, _, outside = three
    monkeypatch.chdir(outside)
    path = str(a / "pipelines" / "orders" / "pipeline.yaml")
    assert _root_of(_invoke("--project", str(a), "run", path, "--json")) == a.resolve()


def test_the_variable_is_ignored_for_a_path(three, monkeypatch) -> None:
    a, b, _, outside = three
    monkeypatch.chdir(outside)
    path = str(a / "pipelines" / "orders" / "pipeline.yaml")
    assert _root_of(_invoke("run", path, "--json", env={"DECOY_PROJECT": str(b)})) == a.resolve()


def test_project_flag_on_a_folder_without_a_marker_is_refused(
    three, tmp_path: Path, monkeypatch
) -> None:
    outside = three[3]
    monkeypatch.chdir(outside)
    result = _invoke("--project", str(outside), "run", "orders", "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert _body(result)["code"] == "layout.project_not_found"
    missing = _invoke("--project", str(tmp_path / "gone"), "validate", "orders", "--json")
    assert missing.exit_code == EXIT_USAGE
    assert _body(missing)["code"] == "layout.project_not_found"


def test_a_name_whose_folder_holds_a_nested_marker_is_a_mismatch(three, monkeypatch) -> None:
    a, *_ = three
    (a / "pipelines" / "orders" / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    monkeypatch.chdir(a)
    result = _invoke("run", "orders", "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert _body(result)["code"] == "layout.project_mismatch"
    assert not (a / "out").exists() and not (a / "pipelines" / "orders" / "out").exists()


def test_a_selected_project_places_output_where_the_walk_does(three, monkeypatch) -> None:
    a, _, _, outside = three
    monkeypatch.chdir(outside)
    doc = _body(_invoke("--project", str(a), "run", "orders", "--json"))
    assert Path(doc["output_dir"]).parent == (a / "out" / "orders").resolve()
    assert list(outside.iterdir()) == []
