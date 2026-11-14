"""AT-14 and AT-28 (P7): `decoy init` makes pipelines inside a project, or a file with `-o`.

In a project `init NAME [--source FILE]` writes `pipelines/NAME/pipeline.yaml`; the source path is
relative to that folder when the source is inside the project and absolute otherwise, and the
target is the bare `<stem>.masked.<ext>` that `run` places in a run folder. `-o FILE` works
anywhere and writes the source relative to FILE's folder; `-o -` writes no file. Outside a
project, without `-o`, `init` refuses before it asks anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    return folder


def _csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"city": ["Austin", "Boston", "Denver"], "note": ["a", "b", "c"]}).to_csv(
        path, index=False
    )
    return path


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "work" / "acme"
    for folder in ("pipelines", "out"):
        (root / folder).mkdir(parents=True)
    (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    return root


def _doc(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _outputs(folder: Path, name: str) -> list[Path]:
    return sorted(folder.rglob(name))


def _files(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*")}


# ---- AT-14: `-o` ---------------------------------------------------------------------------


def test_output_file_writes_a_source_relative_to_it_and_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    _csv(work / "data.csv")
    monkeypatch.chdir(work)

    result = runner.invoke(app, ["init", "-o", "sub/p.yaml", "data.csv", "--quiet"])

    assert result.exit_code == EXIT_OK, result.output
    doc = _doc(work / "sub" / "p.yaml")
    assert doc["sources"]["data"]["path"] == "../data.csv"
    assert doc["targets"]["data"]["path"] == "data.masked.csv"
    ran = runner.invoke(app, ["run", "sub/p.yaml", "--quiet"])
    assert ran.exit_code == EXIT_OK, ran.output
    assert len(_outputs(work / "sub" / "out", "data.masked.csv")) == 1


def test_output_dash_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    _csv(work / "data.csv")
    monkeypatch.chdir(work)
    before = _files(work)

    result = runner.invoke(app, ["init", "-o", "-", "data.csv"])

    assert result.exit_code == EXIT_OK, result.output
    assert "version: 2" in result.stdout
    assert _files(work) == before


def test_output_file_needs_no_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    monkeypatch.chdir(work)
    result = runner.invoke(app, ["init", "--preset", "minimal", "-o", "p.yaml", "--quiet"])
    assert result.exit_code == EXIT_OK, result.output
    assert (work / "p.yaml").is_file()


# ---- AT-28: init inside a project ----------------------------------------------------------


def test_in_project_source_is_relative_the_target_is_bare_and_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _csv(root / "data" / "members.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "members-mask", "--source", "data/members.csv", "--quiet"])

    assert result.exit_code == EXIT_OK, result.output
    yaml_path = root / "pipelines" / "members-mask" / "pipeline.yaml"
    doc = _doc(yaml_path)
    assert doc["sources"]["data"]["path"] == "../../data/members.csv"
    assert doc["targets"]["data"]["path"] == "members.masked.csv"
    assert "name" not in doc  # the folder is the name
    assert not (root / "pipeline.yaml").exists()
    ran = runner.invoke(app, ["run", "members-mask", "--quiet"])
    assert ran.exit_code == EXIT_OK, ran.output
    assert len(_outputs(root / "out" / "members-mask", "members.masked.csv")) == 1


def test_a_source_outside_the_project_is_written_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    outside = _csv(tmp_path / "elsewhere" / "claims.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "claims", "--source", str(outside), "--quiet"])

    assert result.exit_code == EXIT_OK, result.output
    written = _doc(root / "pipelines" / "claims" / "pipeline.yaml")["sources"]["data"]["path"]
    assert Path(written).is_absolute()
    assert Path(written).resolve() == outside.resolve()
    assert _doc(root / "pipelines" / "claims" / "pipeline.yaml")["targets"]["data"]["path"] == (
        "claims.masked.csv"
    )


def test_a_file_argument_names_the_pipeline_after_its_stem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _csv(root / "data.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "data.csv", "--quiet"])

    assert result.exit_code == EXIT_OK, result.output
    doc = _doc(root / "pipelines" / "data" / "pipeline.yaml")
    assert doc["sources"]["data"]["path"] == "../../data.csv"


def test_a_pipeline_that_exists_needs_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    args = ["init", "orders", "--preset", "minimal"]
    assert runner.invoke(app, [*args, "--quiet"]).exit_code == EXIT_OK
    target = root / "pipelines" / "orders" / "pipeline.yaml"
    target.write_text("# edited\n", encoding="utf-8")

    refused = runner.invoke(app, [*args, "--json"])
    assert refused.exit_code == EXIT_USAGE, refused.output
    assert target.read_text(encoding="utf-8") == "# edited\n"

    again = runner.invoke(app, [*args, "--yes", "--quiet"])
    assert again.exit_code == EXIT_OK, again.output
    assert target.read_text(encoding="utf-8") != "# edited\n"


def test_outside_a_project_without_output_it_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    _csv(work / "data.csv")
    monkeypatch.chdir(work)
    before = _files(work)

    result = runner.invoke(app, ["init", "data.csv", "--json"])

    assert result.exit_code == EXIT_USAGE, result.output
    payload = json.loads(result.stdout)
    assert payload["code"] == "layout.project_not_found"
    assert "project new" in payload["error"]
    assert _files(work) == before


def test_outside_a_project_with_no_argument_refuses_before_any_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    monkeypatch.chdir(work)

    result = runner.invoke(app, ["init"], input="minimal\nname\n\n\n")

    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.project_not_found" in result.output
    assert "Preset" not in result.output and "name" not in result.stdout.lower().split("error")[0]
    assert _files(work) == set()


def test_inside_a_project_with_no_argument_the_wizard_asks_for_the_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "--preset", "minimal"], input="wizard\n\n\n")

    assert result.exit_code == EXIT_OK, result.output
    assert "Pipeline name" in result.output
    assert (root / "pipelines" / "wizard" / "pipeline.yaml").is_file()


def test_no_name_in_a_non_interactive_mode_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "--preset", "minimal", "--json"])

    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["status"] == "error"
    assert list((root / "pipelines").iterdir()) == []


@pytest.mark.parametrize("bad", ["../escape", "bad name", "a/b"])
def test_an_invalid_name_is_refused_with_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", bad, "--preset", "minimal", "--json"])

    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["code"] == "layout.pipeline_name_invalid"
    assert list((root / "pipelines").iterdir()) == []
    assert not (tmp_path / "work" / "escape").exists()


def test_a_missing_data_file_is_still_reported_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["init", "missing.csv", "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "does not exist" in json.loads(result.stdout)["error"]


def test_the_project_option_picks_the_project_without_cd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(
        app, ["--project", str(root), "init", "orders", "--preset", "minimal", "--quiet"]
    )

    assert result.exit_code == EXIT_OK, result.output
    assert (root / "pipelines" / "orders" / "pipeline.yaml").is_file()
    assert _files(elsewhere) == set()


def test_json_names_the_pipeline_and_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _csv(root / "data.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "orders", "--source", "data.csv", "--json"])

    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.stdout)
    assert payload["name"] == "orders"
    assert Path(payload["project"]).resolve() == root.resolve()
    assert Path(payload["out"]).resolve() == (root / "pipelines/orders/pipeline.yaml").resolve()


def test_a_source_named_with_a_preset_goes_into_the_template_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _csv(root / "data" / "orders.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(
        app, ["init", "orders", "--preset", "minimal", "--source", "data/orders.csv", "--quiet"]
    )

    assert result.exit_code == EXIT_OK, result.output
    doc = _doc(root / "pipelines" / "orders" / "pipeline.yaml")
    (source_entry,) = doc["sources"].values()
    (target_entry,) = doc["targets"].values()
    assert source_entry["path"] == "../../data/orders.csv"
    assert target_entry["path"] == "orders.masked.csv"


@pytest.mark.parametrize("preset_args", [["--preset", "minimal"], ["--preset", "generate"]])
def test_a_planted_link_is_refused_and_the_outside_file_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preset_args: list[str]
) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.yaml"
    victim.write_text("keep\n", encoding="utf-8")
    monkeypatch.chdir(root)

    # A link at pipeline.yaml.
    (root / "pipelines" / "a").mkdir()
    (root / "pipelines" / "a" / "pipeline.yaml").symlink_to(victim)
    first = runner.invoke(app, ["init", "a", *preset_args, "--yes", "--json"])
    assert first.exit_code == EXIT_USAGE, first.output
    assert victim.read_text(encoding="utf-8") == "keep\n"

    # A link at the pipeline's folder.
    (root / "pipelines" / "b").symlink_to(outside, target_is_directory=True)
    second = runner.invoke(app, ["init", "b", *preset_args, "--yes", "--json"])
    assert second.exit_code == EXIT_USAGE, second.output
    assert sorted(p.name for p in outside.iterdir()) == ["victim.yaml"]
    assert victim.read_text(encoding="utf-8") == "keep\n"


def _people_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "first_name": ["Ann", "Bo"],
            "last_name": ["Lee", "Roe"],
            "email": ["a@x.test", "b@x.test"],
            "ssn": ["111-22-3333", "222-33-4444"],
            "account_status": ["open", "closed"],
        }
    ).to_csv(path, index=False)
    return path


def test_the_wizard_writes_a_typed_cwd_relative_source_relative_to_the_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _people_csv(root / "data" / "orders.csv")
    monkeypatch.chdir(root)

    result = runner.invoke(
        app, ["init", "--preset", "minimal"], input="orders\ndata/orders.csv\n\n"
    )

    assert result.exit_code == EXIT_OK, result.output
    doc = _doc(root / "pipelines" / "orders" / "pipeline.yaml")
    (source_entry,) = doc["sources"].values()
    assert source_entry["path"] == "../../data/orders.csv"
    ran = runner.invoke(app, ["run", "orders", "--quiet"])
    assert ran.exit_code == EXIT_OK, ran.output


def test_the_wizard_with_output_file_writes_the_source_relative_to_that_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "plain"
    work.mkdir()
    _people_csv(work / "orders.csv")
    monkeypatch.chdir(work)

    result = runner.invoke(
        app, ["init", "--preset", "minimal", "-o", "sub/p.yaml"], input="orders.csv\n\n"
    )

    assert result.exit_code == EXIT_OK, result.output
    (source_entry,) = _doc(work / "sub" / "p.yaml")["sources"].values()
    assert source_entry["path"] == "../orders.csv"
    ran = runner.invoke(app, ["run", "sub/p.yaml", "--quiet"])
    assert ran.exit_code == EXIT_OK, ran.output


def test_a_name_that_matches_an_extensionless_file_is_still_a_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    (root / "orders").write_text("not data\n", encoding="utf-8")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "orders", "--preset", "minimal", "--quiet"])

    assert result.exit_code == EXIT_OK, result.output
    assert (root / "pipelines" / "orders" / "pipeline.yaml").is_file()


def test_a_failed_generate_fit_leaves_no_pipeline_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    (root / "empty.csv").write_text("", encoding="utf-8")
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["init", "gen", "--preset", "generate", "--source", "empty.csv"])

    assert result.exit_code != EXIT_OK
    assert not (root / "pipelines" / "gen").exists()
