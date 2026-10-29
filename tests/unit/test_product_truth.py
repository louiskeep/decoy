"""Product copy keeps four different claims apart.

Detection candidates (Pre-scan), measured fidelity and report-only integrity
(Post-scan), artifact integrity (`report verify`) and a release decision are
different claims. No CLI surface may let one stand in for another.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()
README = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def test_readme_names_the_three_phases_and_separates_the_claims() -> None:
    text = _norm(README)
    for phrase in ("pre-scan", "transform", "post-scan"):
        assert phrase in text
    assert "fidelity is not a privacy guarantee" in text
    assert "four different things" in text


def test_help_never_calls_fidelity_privacy_or_integrity_a_release_decision() -> None:
    for argv in (["post-scan", "fidelity", "--help"], ["post-scan", "integrity", "--help"]):
        out = _norm(runner.invoke(app, argv).output)
        assert "not a privacy guarantee" in out or "not a release decision" in out or "report-only" in out
        for banned in ("release-approved", "guaranteed private", "certified safe"):
            assert banned not in out


def test_explain_topics_describe_post_scan_as_report_only() -> None:
    out = _norm(json.loads(runner.invoke(app, ["explain", "post-scan", "--json"]).stdout)["body"])
    assert "not a privacy guarantee" in out
    assert "report-only" in out
    assert "not a release decision" in out
    assert "not a privacy check" in out


def test_explain_pipeline_states_the_lifecycle_and_v2_config() -> None:
    out = _norm(json.loads(runner.invoke(app, ["explain", "pipeline", "--json"]).stdout)["body"])
    for phrase in ("pre-scan", "transform", "post-scan", "post_scan", "version 1 is rejected"):
        assert phrase in out


def test_pre_scan_help_frames_candidates_as_suggestions() -> None:
    out = _norm(runner.invoke(app, ["pre-scan", "--help"]).output)
    assert "suggestions" in out
    assert "not authoritative" in out
