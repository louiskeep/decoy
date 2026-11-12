"""AT-4 and AT-16 (P4): the gate refuses layout faults before any source is read.

`validate`, `ci check` and `run` share the gate's config layer, which runs the layout checks
that need no write (plan 3.14): escape, the Windows path budget, the project marker, and the
pipeline name and claim (read only). An escaping relative output path exits 1
`layout.output_path_escapes` before a source is read; the write-time check in `place_target`
stays behind it. The preflight overwrite advisory no longer looks at a relative target, which
lands in a new run folder.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.ci.rule_codes import validation_codes
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import (
    LayoutError,
    PipelineName,
    RunLayout,
    mint_invocation_id,
)
from tests.ci_support import ci_check, ci_manifest, commit_all, make_repo, parse_stdout, write
from tests.csv_sources import csv_source

runner = CliRunner()
ESCAPES = "layout.output_path_escapes"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    return root


def _config(root: Path, target: str = "masked.csv", **extra: object) -> dict:
    src = root / "a.csv"
    pd.DataFrame({"email": ["a@example.com", "b@example.com"]}).to_csv(src, index=False)
    cfg: dict = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": target}},
    }
    cfg.update(extra)
    return cfg


def _write(root: Path, rel: str, cfg: dict) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _quarantine(path: str) -> dict:
    return {"quarantine": {"enabled": True, "output_path": path}}


@pytest.fixture
def read_spy(monkeypatch) -> list[str]:
    """Records every source read: the gate's preflight reads and the run's own readers."""
    import decoy.cli.preflight as preflight
    from decoy.cli.run import _execute

    seen: list[str] = []

    def spy(name: str, real):
        def wrapper(*args, **kwargs):
            seen.append(name)
            return real(*args, **kwargs)

        return wrapper

    for module, name in (
        (preflight, "_check_source_files"),
        (preflight, "_check_capacity"),
        (_execute, "read_source"),
        (_execute, "iter_source_chunks"),
    ):
        monkeypatch.setattr(module, name, spy(name, getattr(module, name)))
    return seen


def _codes(output: str) -> list[str]:
    document = json.loads(output)
    entries = document.get("messages", document.get("checks", []))
    return [entry.get("code") for entry in entries]


# --- AT-4 escape -------------------------------------------------------------------------

BAD_TARGETS = ["../../x.csv", ".", "", "sub/", "a\x00b.csv", "a\\b.csv", "C:x", "x:y"]


@pytest.mark.parametrize("command", [["validate"], ["validate", "preflight"]])
@pytest.mark.parametrize("target", BAD_TARGETS)
def test_validate_refuses_an_escaping_target_before_a_source_read(
    tmp_path: Path, command: list[str], target: str, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, target))
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert read_spy == []


@pytest.mark.parametrize("target", BAD_TARGETS)
def test_run_refuses_an_escaping_target_before_a_source_read(
    tmp_path: Path, target: str, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, target))
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert read_spy == []
    assert not (tmp_path / "x.csv").exists()
    assert not (root / "out").exists()


@pytest.mark.parametrize("command", [["validate"], ["validate", "preflight"], ["run"]])
def test_an_escaping_quarantine_path_is_refused_before_a_source_read(
    tmp_path: Path, command: list[str], read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    cfg_dict = _config(root, **_quarantine("../../q.jsonl"))
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert read_spy == []


@pytest.mark.parametrize("target", [*BAD_TARGETS, "masked.csv#quarantine"])
def test_ci_check_refuses_an_escaping_output_path(tmp_path: Path, target: str) -> None:
    repo = make_repo(tmp_path / "repo")
    if target.endswith("#quarantine"):
        cfg = _config(repo, "masked.csv", **_quarantine("../../q.jsonl"))
    else:
        cfg = _config(repo, target)
    _write(repo, "pipeline.yaml", cfg)
    write(repo, ".decoy-ci.yaml", ci_manifest())
    commit_all(repo)
    proc = ci_check(repo, "--format", "json")
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert f"validate.{ESCAPES}" in [f["rule_id"] for f in report["findings"]]


def test_a_dotted_path_that_stays_inside_is_accepted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, "a/../b.csv"))
    assert runner.invoke(app, ["validate", str(cfg)]).exit_code == EXIT_OK
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_OK, result.output
    (run,) = [p for p in (root / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    assert (run / "b.csv").is_file()


@pytest.mark.parametrize("target", ["https://example.test/out.csv", "s3://bucket/out.csv"])
def test_a_file_target_url_is_refused_without_echoing_it(tmp_path: Path, target: str) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, target))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert target not in result.output


def test_url_like_text_after_an_escape_is_not_a_url(tmp_path: Path) -> None:
    root = _project(tmp_path)
    target = "../../a://b.csv"
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, target))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)


@posix_only
def test_an_out_link_leaving_the_project_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "out").symlink_to(outside, target_is_directory=True)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in result.output
    assert list(outside.iterdir()) == []


@posix_only
def test_a_symlink_ancestor_cannot_leave_a_typed_out_dir(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    build = tmp_path / "build"
    build.mkdir()
    (build / "esc").symlink_to(outside, target_is_directory=True)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, "esc/x.csv"))
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert list(outside.iterdir()) == []


def test_chunked_with_quarantine_refuses_before_a_source_read(
    tmp_path: Path, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, **_quarantine("q.jsonl")))
    result = runner.invoke(app, ["run", str(cfg), "--chunked"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "read_source" not in read_spy
    assert "iter_source_chunks" not in read_spy


@pytest.mark.parametrize("raw", ["../../x.csv", ".", "", "sub/"])
def test_place_target_refuses_directly(tmp_path: Path, raw: str) -> None:
    layout = RunLayout.open(
        _project(tmp_path),
        PipelineName("orders", True, "pipelines/orders/pipeline.yaml"),
        mint_invocation_id(),
    )
    with pytest.raises(LayoutError) as raised:
        layout.place_target(raw)
    assert raised.value.code == ESCAPES


def test_every_layout_gate_code_is_a_ci_rule_code() -> None:
    from decoy.cli.io import GATE_CODES

    assert GATE_CODES <= validation_codes()


# --- the other gate layout checks (plan 3.14) --------------------------------------------


def test_the_gate_refuses_an_invalid_declared_name(tmp_path: Path, read_spy: list[str]) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "jobs/orders.yaml", _config(root, name="bad name"))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    # The engine schema owns the name rule, so its code comes first; nothing is read.
    assert any(c.endswith("pipeline_name_invalid") for c in _codes(result.output))
    assert read_spy == []


def test_the_gate_refuses_a_name_that_differs_from_its_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, name="sales"))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.pipeline_name_mismatch" in _codes(result.output)


def test_the_gate_reads_a_claim_without_writing_one(tmp_path: Path) -> None:
    root = _project(tmp_path)
    claim = root / "out" / "orders" / "PIPELINE"
    claim.parent.mkdir(parents=True)
    claim.write_text("jobs/first.yaml\n", encoding="utf-8")
    cfg = _write(root, "jobs/second.yaml", _config(root, name="orders"))
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.pipeline_name_collision" in _codes(result.output)
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


def test_the_gate_refuses_an_invalid_marker(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "decoy.yaml").write_text("kind: other\n", encoding="utf-8")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.project_marker_invalid" in _codes(result.output)


def test_validate_writes_no_out_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    assert runner.invoke(app, ["validate", str(cfg)]).exit_code == EXIT_OK
    assert not (root / "out").exists()


def test_the_gate_checks_the_windows_path_budget(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    long_rel = "/".join(["d" * 60] * 5) + "/masked.csv"
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, long_rel))
    assert runner.invoke(app, ["validate", str(cfg)]).exit_code == EXIT_OK
    monkeypatch.setattr("decoy.cli.io._layout._on_windows", lambda: True)
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.path_too_long" in _codes(result.output)


def test_a_config_with_only_absolute_targets_skips_the_project_checks(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "decoy.yaml").write_text("kind: other\n", encoding="utf-8")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, str(tmp_path / "abs.csv")))
    result = runner.invoke(app, ["validate", str(cfg), "--json"])
    assert result.exit_code == EXIT_OK, result.output


# --- AT-16 preflight ---------------------------------------------------------------------


@pytest.mark.parametrize("command", [["validate"], ["validate", "preflight"]])
def test_a_placed_relative_target_gets_no_overwrite_or_folder_warning(
    tmp_path: Path, monkeypatch, command: list[str]
) -> None:
    root = _project(tmp_path)
    cfg_dict = _config(root, "masked.csv")
    cfg_dict["targets"]["b"] = {"type": "file", "format": "csv", "path": "sub/b.csv"}
    cfg_dict["sources"]["b"] = cfg_dict["sources"]["a"]
    cfg_dict["tables"].append({"name": "b", "columns": [{"name": "email", "strategy": "redact"}]})
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    # A file of the same name where the old rule looked (the current folder) must not matter.
    monkeypatch.chdir(root)
    (root / "masked.csv").write_text("x\n", encoding="utf-8")
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert "would_overwrite" not in result.output
    assert "parent_missing" not in result.output


@pytest.mark.parametrize("command", [["validate"], ["validate", "preflight"]])
def test_an_existing_absolute_target_still_warns(tmp_path: Path, command: list[str]) -> None:
    root = _project(tmp_path)
    target = tmp_path / "abs.csv"
    target.write_text("x\n", encoding="utf-8")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, str(target)))
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert "would_overwrite" in result.output


def test_no_source_row_value_reaches_an_escape_refusal(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, "../../x.csv"))
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE
    assert "a@example.com" not in result.output
    assert os.fspath(tmp_path / "x.csv") not in result.output


# --- AT-30 the placement matrix (plan 3.6.1 A) ---------------------------------------------

COLLISION = "layout.output_path_collision"
UNUSABLE = "layout.output_dir_unusable"


def _break_marker(root: Path) -> None:
    (root / "decoy.yaml").write_text("kind: other\n", encoding="utf-8")


def _generate_config(root: Path, target: str = "g.csv") -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {},
        "tables": [
            {
                "name": "g",
                "row_count": 10,
                "generate_columns": [{"name": "pid", "type": "sequence", "start": 1, "step": 1}],
            }
        ],
        "targets": {"g": {"type": "file", "format": "csv", "path": target}},
    }
    return _write(root, "pipelines/gen/pipeline.yaml", cfg)


def test_layout_gate_matrix_out_dir_skips_project_checks(
    tmp_path: Path, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    _break_marker(root)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    build = tmp_path / "build"
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build), "--json"])
    assert result.exit_code == EXIT_OK, result.output
    assert (build / "masked.csv").is_file()
    assert not (root / "out").exists()


def test_layout_gate_matrix_preflight_keeps_project_checks(
    tmp_path: Path, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    _break_marker(root)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    result = runner.invoke(app, ["validate", "preflight", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.project_marker_invalid" in _codes(result.output)
    assert read_spy == []


@pytest.mark.usefixtures("mask_secret")
def test_layout_gate_matrix_preview_skips_layout_checks(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _break_marker(root)
    cfg = _generate_config(root)
    result = runner.invoke(app, ["run", str(cfg), "--rows", "5", "--json"])
    assert result.exit_code == EXIT_OK, result.output
    assert not (root / "out").exists()


@pytest.mark.usefixtures("mask_secret")
def test_layout_gate_matrix_preview_skips_the_escape_check(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _generate_config(root, "../../g.csv")
    result = runner.invoke(app, ["run", str(cfg), "--rows", "5", "--json"])
    assert result.exit_code == EXIT_OK, result.output


def test_layout_gate_matrix_out_dir_budget_runs_against_the_directory(
    tmp_path: Path, monkeypatch, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    _break_marker(root)
    long_rel = "/".join(["d" * 60] * 5) + "/masked.csv"
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, long_rel))
    build = tmp_path / "build"
    build.mkdir()
    monkeypatch.setattr("decoy.cli.io._layout._on_windows", lambda: True)
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "layout.path_too_long" in _codes(result.output)
    assert read_spy == []


def test_layout_gate_matrix_out_dir_target_that_exists_warns(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    build = tmp_path / "build"
    build.mkdir()
    (build / "masked.csv").write_text("old\n", encoding="utf-8")
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert "1 pre-run warning(s)" in result.output


def test_layout_gate_matrix_out_dir_with_no_old_file_does_not_warn(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    build = tmp_path / "build"
    build.mkdir()
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert "pre-run warning" not in result.output


@pytest.mark.parametrize("kind", ["file", "dangling", "missing_parent"])
def test_layout_gate_matrix_unusable_out_dir_refuses_value_free(
    tmp_path: Path, read_spy: list[str], kind: str
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root))
    build = tmp_path / "bld" / "deeper" if kind == "missing_parent" else tmp_path / "build"
    if kind == "file":
        build.write_text("x", encoding="utf-8")
    elif kind == "dangling":
        build.symlink_to(tmp_path / "nowhere")
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert UNUSABLE in result.output
    assert str(build) not in result.output
    assert read_spy == []


def test_layout_gate_matrix_unused_out_dir_is_not_created(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, str(tmp_path / "abs.csv")))
    build = tmp_path / "build"
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_OK, result.output
    assert not build.exists()


def test_layout_gate_matrix_refused_out_dir_run_creates_no_directory(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, "../../x.csv"))
    build = tmp_path / "build"
    result = runner.invoke(app, ["run", str(cfg), "--out-dir", str(build)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not build.exists()


# --- AT-31 destination collisions (plan 3.6.1 B) -------------------------------------------


def _two_tables(root: Path, first: str, second: str, **extra: object) -> dict:
    cfg = _config(root, first, **extra)
    cfg["sources"]["b"] = cfg["sources"]["a"]
    cfg["tables"].append({"name": "b", "columns": [{"name": "email", "strategy": "redact"}]})
    cfg["targets"]["b"] = {"type": "file", "format": "csv", "path": second}
    return cfg


def _assert_collision(result, first: str, second: str, spy: list[str]) -> None:
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output
    assert first in result.output and second in result.output
    assert read_spy_empty(spy)


def read_spy_empty(spy: list[str]) -> bool:
    return spy == []


@pytest.mark.parametrize("mode", ["project", "out_dir", "preflight"])
def test_resolved_output_collisions_refuse_before_source_two_tables(
    tmp_path: Path, read_spy: list[str], mode: str
) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, "m.csv", "./m.csv"))
    build = tmp_path / "build"
    args = {
        "project": ["run", str(cfg), "--json"],
        "out_dir": ["run", str(cfg), "--out-dir", str(build), "--json"],
        "preflight": ["validate", "preflight", str(cfg), "--json"],
    }[mode]
    result = runner.invoke(app, args)
    _assert_collision(result, "targets.a.path", "targets.b.path", read_spy)
    assert not (root / "out").exists()
    assert not build.exists()


def test_resolved_output_collisions_target_and_quarantine(
    tmp_path: Path, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    cfg = _write(
        root, "pipelines/orders/pipeline.yaml", _config(root, "m.csv", **_quarantine("m.csv"))
    )
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    _assert_collision(result, "targets.a.path", "quarantine.output_path", read_spy)


@pytest.mark.parametrize("command", [["run"], ["validate", "preflight"]])
def test_resolved_output_collisions_equal_absolute_targets(
    tmp_path: Path, read_spy: list[str], command: list[str]
) -> None:
    root = _project(tmp_path)
    same = str(tmp_path / "abs.csv")
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, same, same))
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    _assert_collision(result, "targets.a.path", "targets.b.path", read_spy)
    assert not (tmp_path / "abs.csv").exists()
    assert same not in result.output


@posix_only
def test_resolved_output_collisions_two_spellings_through_a_symlink(
    tmp_path: Path, read_spy: list[str]
) -> None:
    root = _project(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    cfg_dict = _two_tables(root, str(real / "o.csv"), str(tmp_path / "alias" / "o.csv"))
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    result = runner.invoke(app, ["validate", "preflight", str(cfg), "--json"])
    _assert_collision(result, "targets.a.path", "targets.b.path", read_spy)


def test_resolved_output_collisions_case_only_names_on_a_folding_parent(
    tmp_path: Path, read_spy: list[str], monkeypatch
) -> None:
    from decoy.cli.io import _placement

    monkeypatch.setattr(_placement, "_folds_case", lambda _folder: True)
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, "Out.csv", "out.csv"))
    result = runner.invoke(app, ["validate", "preflight", str(cfg), "--json"])
    _assert_collision(result, "targets.a.path", "targets.b.path", read_spy)


def test_resolved_output_collisions_case_only_names_on_a_sensitive_parent_pass(
    tmp_path: Path, monkeypatch
) -> None:
    from decoy.cli.io import _placement

    monkeypatch.setattr(_placement, "_folds_case", lambda _folder: False)
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, "Out.csv", "out.csv"))
    assert runner.invoke(app, ["validate", "preflight", str(cfg)]).exit_code == EXIT_OK


@pytest.mark.parametrize(
    ("flag", "other"),
    [("--evidence-out", "target"), ("--vault", "target"), ("--vault", "--evidence-out")],
)
def test_resolved_output_collisions_typed_files(
    tmp_path: Path, read_spy: list[str], flag: str, other: str
) -> None:
    root = _project(tmp_path)
    typed = tmp_path / "t.csv"
    target = typed if other == "target" else tmp_path / "other.csv"
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, str(target)))
    args = ["run", str(cfg), "--json", flag, str(typed)]
    if other != "target":
        args += [other, str(typed)]
    result = runner.invoke(app, args)
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output
    assert (flag if other == "target" else other) in result.output
    assert read_spy == []
    assert not typed.exists()


def test_resolved_output_collisions_distinct_outputs_pass(tmp_path: Path) -> None:
    root = _project(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, "a.csv", "b.csv"))
    assert runner.invoke(app, ["validate", "preflight", str(cfg)]).exit_code == EXIT_OK


# --- AT-31 a dangling final symlink is the destination the writer publishes onto ---------------


def _dangling(tmp_path: Path) -> tuple[Path, Path]:
    """`alias.csv -> real.csv` where `real.csv` does not exist yet: `(alias, real)`."""
    real = tmp_path / "real.csv"
    alias = tmp_path / "alias.csv"
    alias.symlink_to(real)
    return alias, real


@posix_only
@pytest.mark.parametrize("command", [["run"], ["validate", "preflight"]])
@pytest.mark.parametrize("order", ["alias_first", "target_first"])
def test_a_dangling_symlink_collides_with_its_target_for_two_tables(
    tmp_path: Path, read_spy: list[str], command: list[str], order: str
) -> None:
    root = _project(tmp_path)
    alias, real = _dangling(tmp_path)
    first, second = (alias, real) if order == "alias_first" else (real, alias)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _two_tables(root, str(first), str(second)))
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in _codes(result.output)
    assert read_spy == []
    assert not real.exists()


@posix_only
@pytest.mark.parametrize("command", [["run"], ["validate", "preflight"]])
def test_a_dangling_symlink_collides_with_a_quarantine_file(
    tmp_path: Path, read_spy: list[str], command: list[str]
) -> None:
    root = _project(tmp_path)
    alias, real = _dangling(tmp_path)
    cfg_dict = _config(root, str(real), **_quarantine(str(alias)))
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in _codes(result.output)
    assert read_spy == []
    assert not real.exists()


@posix_only
@pytest.mark.parametrize("flag", ["--vault", "--evidence-out"])
def test_a_dangling_symlink_collides_with_a_typed_side_file(
    tmp_path: Path, read_spy: list[str], flag: str
) -> None:
    root = _project(tmp_path)
    alias, real = _dangling(tmp_path)
    cfg = _write(root, "pipelines/orders/pipeline.yaml", _config(root, str(real)))
    result = runner.invoke(app, ["run", str(cfg), "--json", flag, str(alias)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in _codes(result.output)
    assert read_spy == []
    assert not real.exists()


# --- AT-4 a NUL byte in an absolute destination -------------------------------------------------


@pytest.mark.parametrize("command", [["validate"], ["validate", "preflight"], ["run"]])
@pytest.mark.parametrize("where", ["target", "quarantine"])
def test_a_nul_in_an_absolute_destination_is_refused_before_a_source_read(
    tmp_path: Path, read_spy: list[str], command: list[str], where: str
) -> None:
    root = _project(tmp_path)
    bad = str(tmp_path / "a\x00b.csv")
    cfg_dict = _config(root, bad) if where == "target" else _config(root, **_quarantine(bad))
    cfg = _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)
    result = runner.invoke(app, [*command, str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert ESCAPES in _codes(result.output)
    assert read_spy == []
    assert "a\\u0000b" not in result.output
