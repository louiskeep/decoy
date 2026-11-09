"""Report and scan output a first-time user misread.

`report fidelity` printed PASS beside grade F, `report integrity` hid which
columns leaked unless `--json` was set, the reid risk had no unit, and
`ci check` with no manifest said nothing on stderr.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_USAGE
from tests.ci_support import make_repo, run_decoy

runner = CliRunner()

_NOT_ENFORCED = "threshold violation(s) not enforced (use --mode fail)"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _drifted_pair(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame({"a": list(range(50))}).to_csv(src, index=False)
    pd.DataFrame({"a": [999] * 50}).to_csv(out, index=False)
    return src, out


def _fidelity(src: Path, out: Path, *flags: str) -> tuple[object, dict]:
    human = runner.invoke(app, ["report", "fidelity", str(src), str(out), *flags])
    machine = runner.invoke(app, ["report", "fidelity", str(src), str(out), *flags, "--json"])
    return human, json.loads(machine.stdout)


# --- Item 8: report mode never prints PASS -----------------------------------


def test_report_mode_with_no_violations_says_report_only(tmp_path: Path) -> None:
    src = tmp_path / "source.csv"
    pd.DataFrame({"a": list(range(50))}).to_csv(src, index=False)

    human, payload = _fidelity(src, src)

    assert human.exit_code == 0, human.output
    assert payload["policy"]["verdict"] == "pass"
    assert payload["policy"]["violations"] == []
    text = _flat(human.stdout)
    assert "PASS" not in text
    assert "REPORT ONLY (no threshold violations)" in text


def test_min_grade_in_report_mode_is_reported_not_enforced(tmp_path: Path) -> None:
    src, out = _drifted_pair(tmp_path)

    human, payload = _fidelity(src, out, "--min-grade", "B")

    assert human.exit_code == 0, human.output
    assert payload["policy"]["verdict"] == "pass"
    count = len(payload["policy"]["violations"])
    assert count >= 1
    text = _flat(human.stdout)
    assert "PASS" not in text
    assert f"REPORT ONLY: {count} {_NOT_ENFORCED}" in text


def test_strategy_defaults_alone_can_produce_unenforced_violations(tmp_path: Path) -> None:
    src, out = _drifted_pair(tmp_path)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "t", "columns": [{"name": "a", "strategy": "shuffle"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
    }
    cfg_path = tmp_path / "pipeline.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    human, payload = _fidelity(src, out, "--config", str(cfg_path))

    assert human.exit_code == 0, human.output
    assert payload["policy"]["verdict"] == "pass"
    count = len(payload["policy"]["violations"])
    assert count >= 1, payload["policy"]
    assert f"REPORT ONLY: {count} {_NOT_ENFORCED}" in _flat(human.stdout)


def test_fail_mode_still_prints_fail_and_exits_findings(tmp_path: Path) -> None:
    src, out = _drifted_pair(tmp_path)

    human, payload = _fidelity(src, out, "--mode", "fail", "--min-grade", "B")

    assert human.exit_code == EXIT_FINDINGS
    assert payload["policy"]["verdict"] == "fail"
    assert "FAIL" in human.stdout
    assert "REPORT ONLY" not in human.stdout


# --- Item 9: residual-PII findings in human output ---------------------------


@pytest.fixture
def leaky_pair(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src.csv"
    masked = tmp_path / "masked.csv"
    rows = {
        "email": [f"user{i}@example.com" for i in range(30)],
        "ssn": [f"123-45-{6000 + i}" for i in range(30)],
        "ip_address": [f"10.0.0.{i + 1}" for i in range(30)],
    }
    pd.DataFrame(rows).to_csv(src, index=False)
    pd.DataFrame(rows).to_csv(masked, index=False)
    return src, masked


def test_integrity_human_output_names_each_residual_pii_column(
    leaky_pair: tuple[Path, Path],
) -> None:
    src, masked = leaky_pair
    args = ["report", "integrity", str(masked), "--source", str(src)]
    machine = runner.invoke(app, [*args, "--json"])
    findings = json.loads(machine.stdout)["report"]["residual_pii"]
    assert len(findings) >= 2, findings

    human = runner.invoke(app, args, env={"COLUMNS": "10000"})

    assert human.exit_code == machine.exit_code
    assert "Residual PII findings" in human.stdout
    leading_cells = [line.split()[:4] for line in human.stdout.splitlines()]
    for f in findings:
        expected = [f["table"], f["column"], f["detector_id"], f["severity"]]
        assert expected in leading_cells, f"no row for {expected}:\n{human.stdout}"


# --- Item 10: reid risk carries its scale and k ------------------------------


@pytest.mark.parametrize(("k", "shown"), [(1, "k=1"), (None, "k=n/a")])
def test_scan_reid_risk_names_its_scale_and_k(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, k: int | None, shown: str
) -> None:
    import decoy_engine

    real = decoy_engine.profile_columns

    def profile_with_k(*args, **kwargs):
        profile = real(*args, **kwargs)
        profile.reid_risk_score = 100.0
        profile.k_anonymity = k
        return profile

    monkeypatch.setattr(decoy_engine, "profile_columns", profile_with_k)
    src = tmp_path / "people.csv"
    pd.DataFrame({"zip": ["78701", "02110", "10001"], "age": [30, 41, 52]}).to_csv(src, index=False)

    result = runner.invoke(app, ["scan", str(src)])

    assert result.exit_code == 0, result.output
    assert f"100.0 / 100 ({shown})" in _flat(result.stdout)


def test_scan_diff_reid_risk_delta_is_in_points(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps({"fields": [], "reid_risk_score": 10.0}), encoding="utf-8")
    new.write_text(json.dumps({"fields": [], "reid_risk_score": 11.5}), encoding="utf-8")

    result = runner.invoke(app, ["scan", "diff", str(old), str(new)])

    assert result.exit_code == 0, result.output
    assert "+1.50 points" in _flat(result.stdout)


# --- Item 12: ci check with no manifest --------------------------------------

# The refusal document `ci check` wrote for a missing manifest before the
# stderr hint existed; stdout must stay byte-equal.
_MISSING_MANIFEST_STDOUT = (
    '{"schema_version":"decoy-ci-report/v1","status":"refused","exit_code":1,'
    '"checks":[{"id":"manifest","kind":"manifest","status":"refused",'
    '"reason_code":"ci.manifest_unreadable","finding_count":0}],'
    '"notes":[],"findings":[]}'
    "\n"
)


def test_missing_manifest_prints_a_hint_on_stderr_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")

    proc = run_decoy(["ci", "check"], repo)

    assert proc.returncode == EXIT_USAGE
    assert json.loads(proc.stdout)["checks"][0]["reason_code"] == "ci.manifest_unreadable"
    assert proc.stdout == _MISSING_MANIFEST_STDOUT
    assert ".decoy-ci.yaml" in proc.stderr
    assert "decoy ci --help" in proc.stderr
    assert str(tmp_path) not in proc.stdout + proc.stderr


def test_missing_manifest_names_the_path_as_given(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")

    proc = run_decoy(["ci", "check", "ci/missing.yaml"], repo)

    assert proc.returncode == EXIT_USAGE
    assert "ci/missing.yaml" in proc.stderr
    assert str(tmp_path) not in proc.stdout + proc.stderr


def test_missing_manifest_quiet_prints_nothing_on_stderr(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")

    proc = run_decoy(["ci", "check", "--quiet"], repo)

    assert proc.returncode == EXIT_USAGE
    assert proc.stderr == ""
