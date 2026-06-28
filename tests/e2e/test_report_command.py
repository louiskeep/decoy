"""E2E tests for ``decoy report render/summarize/compare`` (SP-18).

TDD: these tests assert CLI behavior. They fail first, then the implementation
makes them pass.

Assertions:
P1.  ``report render evidence.json --out report.html`` exits 0; file is created.
P2.  ``report render evidence.json --format markdown --out report.md`` exits 0.
P3.  ``report render`` with missing evidence file exits 1.
P4.  ``report render`` with invalid JSON exits 1.
P5.  ``report summarize evidence.json`` exits 0; key fields appear in output.
P6.  ``report summarize`` with missing evidence file exits 1.
P7.  ``report compare old.json new.json`` exits 0 when no changes.
P8.  ``report compare old.json new.json`` exits 0 and reports changes when
     the pipeline fingerprint differs.
P9.  ``report compare old.json new.json --json`` emits structured JSON.
P10. ``report compare`` with a missing evidence file exits 1.
P11. ``report render`` HTML output contains no external CDN URLs.
P12. ``report render`` HTML output is self-contained (no external script src).
P13. ``report summarize`` output includes pipeline fingerprint prefix.
"""

from __future__ import annotations

import copy
import json as _json
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.evidence import build_manifest

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _minimal_config(src_path: Path, out_path: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src_path)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "cust_ns",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(out_path)},
        },
    }


def _write_evidence(tmp_path: Path, suffix: str = "") -> tuple[Path, dict[str, Any]]:
    """Write fixture files and an evidence manifest.

    Returns (evidence_path, manifest_dict).
    """
    src_path = tmp_path / f"in{suffix}.csv"
    out_path = tmp_path / f"out{suffix}.csv"
    pipeline_path = tmp_path / f"pipeline{suffix}.yaml"
    evidence_path = tmp_path / f"evidence{suffix}.json"

    src_path.write_text("email\nfoo@bar.com\nbaz@qux.com\n", encoding="utf-8")
    out_path.write_text("email\nA@B.com\nC@D.com\n", encoding="utf-8")
    config_dict = _minimal_config(src_path, out_path)
    pipeline_path.write_text(yaml.dump(config_dict), encoding="utf-8")

    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 2}},
        cli_version="0.5.0",
        engine_version="0.4.0",
    )
    evidence_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    return evidence_path, manifest


# ---------------------------------------------------------------------------
# P1: report render HTML
# ---------------------------------------------------------------------------


def test_report_render_html_exits_0(tmp_path: Path) -> None:
    """report render --out report.html exits 0 and creates the file."""
    evidence_path, _ = _write_evidence(tmp_path)
    out_path = tmp_path / "report.html"

    result = runner.invoke(app, ["report", "render", str(evidence_path), "--out", str(out_path)])

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    assert out_path.exists(), "HTML report file was not created"
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE" in content or "<!doctype" in content.lower()


# ---------------------------------------------------------------------------
# P2: report render Markdown
# ---------------------------------------------------------------------------


def test_report_render_markdown_exits_0(tmp_path: Path) -> None:
    """report render --format markdown --out report.md exits 0 and creates file."""
    evidence_path, _ = _write_evidence(tmp_path)
    out_path = tmp_path / "report.md"

    result = runner.invoke(
        app,
        ["report", "render", str(evidence_path), "--format", "markdown", "--out", str(out_path)],
    )

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    assert out_path.exists(), "Markdown report file was not created"
    content = out_path.read_text(encoding="utf-8")
    # Markdown should have at least one heading
    assert "#" in content


# ---------------------------------------------------------------------------
# P3: report render missing file
# ---------------------------------------------------------------------------


def test_report_render_missing_evidence_file(tmp_path: Path) -> None:
    """report render with a missing evidence file exits 1."""
    out_path = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["report", "render", str(tmp_path / "no_such.json"), "--out", str(out_path)],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P4: report render invalid JSON
# ---------------------------------------------------------------------------


def test_report_render_invalid_json(tmp_path: Path) -> None:
    """report render with invalid JSON exits 1 with an error message."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json {broken", encoding="utf-8")
    out_path = tmp_path / "report.html"
    result = runner.invoke(app, ["report", "render", str(bad), "--out", str(out_path)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P5: report summarize
# ---------------------------------------------------------------------------


def test_report_summarize_exits_0(tmp_path: Path) -> None:
    """report summarize exits 0 and prints key fields to stdout."""
    evidence_path, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "summarize", str(evidence_path)])

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    output = result.output
    # Key fields should appear
    assert "cli-local-1" in output or "pipeline" in output.lower() or "run" in output.lower()


# ---------------------------------------------------------------------------
# P6: report summarize missing file
# ---------------------------------------------------------------------------


def test_report_summarize_missing_evidence_file(tmp_path: Path) -> None:
    """report summarize with a missing evidence file exits 1."""
    result = runner.invoke(app, ["report", "summarize", str(tmp_path / "no_such.json")])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P7: report compare no changes
# ---------------------------------------------------------------------------


def test_report_compare_no_changes(tmp_path: Path) -> None:
    """report compare with identical manifests exits 0 and reports no changes."""
    evidence_path, manifest = _write_evidence(tmp_path)
    # Second evidence file with the same content
    evidence_path2 = tmp_path / "evidence2.json"
    evidence_path2.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")

    result = runner.invoke(app, ["report", "compare", str(evidence_path), str(evidence_path2)])

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    output = result.output.lower()
    # Should indicate no changes
    assert "no change" in output or "identical" in output or "0 change" in output


# ---------------------------------------------------------------------------
# P8: report compare detects changed pipeline fingerprint
# ---------------------------------------------------------------------------


def test_report_compare_detects_changed_pipeline_fingerprint(tmp_path: Path) -> None:
    """report compare reports a changed pipeline fingerprint."""
    evidence_path, manifest = _write_evidence(tmp_path)
    new_manifest = copy.deepcopy(manifest)
    new_manifest["pipeline_fingerprint"] = "sha256:" + "b" * 64
    # Recompute manifest_hash so it is internally consistent
    from decoy.cli.evidence import compute_manifest_hash

    new_manifest["manifest_hash"] = compute_manifest_hash(new_manifest)

    evidence_path2 = tmp_path / "evidence2.json"
    evidence_path2.write_text(_json.dumps(new_manifest, indent=2), encoding="utf-8")

    result = runner.invoke(app, ["report", "compare", str(evidence_path), str(evidence_path2)])

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    output = result.output.lower()
    assert "pipeline" in output and ("changed" in output or "differ" in output or "fingerprint" in output)


# ---------------------------------------------------------------------------
# P9: report compare --json
# ---------------------------------------------------------------------------


def test_report_compare_json_output(tmp_path: Path) -> None:
    """report compare --json emits structured JSON."""
    evidence_path, manifest = _write_evidence(tmp_path)
    new_manifest = copy.deepcopy(manifest)
    new_manifest["pipeline_fingerprint"] = "sha256:" + "b" * 64
    from decoy.cli.evidence import compute_manifest_hash

    new_manifest["manifest_hash"] = compute_manifest_hash(new_manifest)

    evidence_path2 = tmp_path / "evidence2.json"
    evidence_path2.write_text(_json.dumps(new_manifest, indent=2), encoding="utf-8")

    result = runner.invoke(
        app, ["report", "compare", str(evidence_path), str(evidence_path2), "--json"]
    )

    assert result.exit_code == 0, f"Expected exit 0; got {result.exit_code}. Output:\n{result.output}"
    data = _json.loads(result.stdout)
    assert "pipeline_fingerprint_changed" in data
    assert data["pipeline_fingerprint_changed"] is True


# ---------------------------------------------------------------------------
# P10: report compare missing file
# ---------------------------------------------------------------------------


def test_report_compare_missing_evidence_file(tmp_path: Path) -> None:
    """report compare with a missing file exits 1."""
    evidence_path, _ = _write_evidence(tmp_path)
    result = runner.invoke(
        app, ["report", "compare", str(evidence_path), str(tmp_path / "no_such.json")]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P11-P12: HTML self-contained (via CLI)
# ---------------------------------------------------------------------------


def test_report_render_html_no_external_cdn(tmp_path: Path) -> None:
    """HTML report produced by the CLI must not contain external CDN URLs."""
    evidence_path, _ = _write_evidence(tmp_path)
    out_path = tmp_path / "report.html"
    runner.invoke(app, ["report", "render", str(evidence_path), "--out", str(out_path)])

    if out_path.exists():
        content = out_path.read_text(encoding="utf-8")
        assert "http://" not in content
        assert "https://" not in content


def test_report_render_html_no_external_script(tmp_path: Path) -> None:
    """HTML report must not contain external script src tags."""
    evidence_path, _ = _write_evidence(tmp_path)
    out_path = tmp_path / "report.html"
    runner.invoke(app, ["report", "render", str(evidence_path), "--out", str(out_path)])

    if out_path.exists():
        content = out_path.read_text(encoding="utf-8").lower()
        assert "<script src" not in content


# ---------------------------------------------------------------------------
# P13: report summarize includes pipeline fingerprint prefix
# ---------------------------------------------------------------------------


def test_report_summarize_includes_pipeline_fingerprint(tmp_path: Path) -> None:
    """report summarize output includes the pipeline fingerprint (sha256: prefix)."""
    evidence_path, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "summarize", str(evidence_path)])

    assert result.exit_code == 0
    assert "sha256:" in result.output
