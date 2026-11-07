"""The pre-run gate reports a target format that contradicts its path suffix.

`decoy validate` and `decoy ci check` agree with `decoy run`, which refuses the same config
with exit 1 (CLI-FMT Part A2). The `decoy ci check` fixture pattern is the one in
tests/e2e/test_ci_exit_codes.py (`ci_support.ci_check`, `ci_manifest`, `parse_stdout`).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.ci.rule_codes import validation_codes
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import _targets
from tests.ci_support import ci_check, ci_manifest, commit_all, make_repo, parse_stdout, write

runner = CliRunner()


def _config(tmp_path: Path, fmt: str, out: str) -> Path:
    src = tmp_path / "in.csv"
    src.write_text("email\na@example.invalid\nb@example.invalid\n", encoding="utf-8")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "people",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "ns",
                    }
                ],
            }
        ],
        "targets": {"people": {"type": "file", "format": fmt, "path": str(tmp_path / out)}},
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _findings(output: str) -> list[dict]:
    doc = json.loads(output)
    return [m for m in doc["messages"] if m.get("code") == _targets.SUFFIX_MISMATCH]


def test_validate_reports_the_contradiction(tmp_path: Path) -> None:
    config = _config(tmp_path, "parquet", "out.csv")
    result = runner.invoke(app, ["validate", str(config), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    (finding,) = _findings(result.output)
    assert finding["layer"] == "config"
    assert finding["severity"] == "error"
    assert finding["location"] == "targets.people.format"
    expected = _targets.target_format_issues(yaml.safe_load(config.read_text()), chunked=False)
    assert finding["message"] == expected[0].message
    # The envelope's own `config` key echoes the path the caller passed; the finding must not.
    assert str(tmp_path) not in json.dumps(finding)


def test_matching_config_has_no_such_finding(tmp_path: Path) -> None:
    config = _config(tmp_path, "csv", "out.csv")
    result = runner.invoke(app, ["validate", str(config), "--json"])
    assert result.exit_code == EXIT_OK, result.output
    assert _findings(result.output) == []


def test_run_still_refuses_the_same_config(tmp_path: Path) -> None:
    config = _config(tmp_path, "parquet", "out.csv")
    gate = runner.invoke(app, ["validate", str(config), "--json"])
    run = runner.invoke(app, ["run", str(config)])
    assert run.exit_code == EXIT_USAGE, run.output
    (finding,) = _findings(gate.output)
    assert " ".join(finding["message"].split()) in " ".join(run.output.split())


def test_ci_check_renders_the_rule_id_not_the_unknown_token(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, "data/in.csv", "email\na@example.invalid\n")
    (repo / "out").mkdir()
    cfg = _config(tmp_path, "parquet", "out.csv")
    write(repo, "pipeline.yaml", cfg.read_text(encoding="utf-8"))
    write(repo, ".decoy-ci.yaml", ci_manifest())
    commit_all(repo)
    proc = ci_check(repo, "--format", "json")
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert "validate.target_format_suffix_mismatch" in [f["rule_id"] for f in report["findings"]]


def test_both_dynamic_codes_are_allowlisted_for_ci() -> None:
    mismatch = {"targets": {"t": {"format": "parquet", "path": "o.csv"}}}
    unknown = {"targets": {"t": {"format": "xml", "path": "o.csv"}}}
    emitted = {
        i.code
        for raw in (mismatch, unknown)
        for i in _targets.target_format_issues(raw, chunked=False)
    }
    assert emitted == {_targets.SUFFIX_MISMATCH, _targets.FORMAT_UNKNOWN}
    assert emitted <= validation_codes()
