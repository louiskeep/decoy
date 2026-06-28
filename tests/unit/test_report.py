"""Unit tests for the report module (SP-18).

TDD: these tests assert behavior of the pure report helpers --
render_html, render_markdown, compare_manifests.

Assertions:
R1.  render_html produces a complete HTML document from a manifest.
R2.  render_html includes key manifest fields in the output.
R3.  render_html is self-contained (no external CDN URLs or script srcs).
R4.  render_html includes an omission disclaimer in the report footer.
R5.  render_markdown produces a Markdown document from a manifest.
R6.  render_markdown includes key manifest fields in the output.
R7.  compare_manifests detects a changed pipeline fingerprint.
R8.  compare_manifests detects a row-count delta.
R9.  compare_manifests detects warnings added between two runs.
R10. compare_manifests detects warnings removed between two runs.
R11. compare_manifests shows no changes when both manifests are identical.
R12. compare_manifests detects changed input fingerprint.
R13. compare_manifests detects changed output fingerprint.
R14. render_html includes strategy names (but never raw values).
R15. render_markdown includes strategy names (but never raw values).
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from decoy.cli.report import compare_manifests, render_html, render_markdown

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    *,
    run_id: str | None = None,
    pipeline_fingerprint: str = "sha256:aaaa" + "0" * 60,
    input_fp: str = "sha256:bbbb" + "0" * 60,
    output_fp: str = "sha256:cccc" + "0" * 60,
    row_counts: dict[str, int] | None = None,
    warnings: list[Any] | None = None,
    timings: list[dict[str, Any]] | None = None,
    strategies: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "cli-local-1",
        "producer": "decoy-cli",
        "run_id": run_id or str(uuid.uuid4()),
        "run_timestamp": "2026-06-28T10:00:00+00:00",
        "cli_version": "0.5.0",
        "engine_version": "0.4.0",
        "pipeline_path": "/tmp/pipeline.yaml",
        "pipeline_fingerprint": pipeline_fingerprint,
        "input_fingerprints": {
            "customers": {
                "path": "/tmp/in.csv",
                "fingerprint": input_fp,
                "fingerprint_method": "full",
                "size_bytes": 1024,
            }
        },
        "output_fingerprints": {
            "customers": {
                "path": "/tmp/out.csv",
                "fingerprint": output_fp,
                "fingerprint_method": "full",
                "size_bytes": 1024,
            }
        },
        "row_counts": row_counts if row_counts is not None else {"customers": 100},
        "key_label": None,
        "warnings": warnings if warnings is not None else [],
        "timings": timings
        if timings is not None
        else [
            {
                "strategy_type": "faker",
                "column": "email",
                "elapsed_ms": 12.5,
                "peak_memory_delta_kb": 4,
            }
        ],
        "strategies": strategies
        if strategies is not None
        else [{"table": "customers", "column": "email", "strategy": "faker"}],
        "manifest_hash": "sha256:" + "a" * 64,
    }


# ---------------------------------------------------------------------------
# R1: render_html produces a complete HTML document
# ---------------------------------------------------------------------------


def test_render_html_produces_html_document() -> None:
    """render_html returns a string that starts with an HTML doctype."""
    manifest = _make_manifest()
    html = render_html(manifest)
    assert isinstance(html, str)
    assert html.strip().lower().startswith("<!doctype html")


def test_render_html_has_html_closing_tag() -> None:
    """render_html returns a complete HTML document (has a closing html tag)."""
    manifest = _make_manifest()
    html = render_html(manifest)
    assert "</html>" in html.lower()


# ---------------------------------------------------------------------------
# R2: render_html includes key manifest fields
# ---------------------------------------------------------------------------


def test_render_html_includes_run_id() -> None:
    """render_html includes the run_id value in the output."""
    fixed_id = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    manifest = _make_manifest(run_id=fixed_id)
    html = render_html(manifest)
    assert fixed_id in html


def test_render_html_includes_schema_version() -> None:
    """render_html includes the schema version."""
    manifest = _make_manifest()
    html = render_html(manifest)
    assert "cli-local-1" in html


def test_render_html_includes_pipeline_fingerprint_prefix() -> None:
    """render_html includes the pipeline fingerprint (at least a prefix)."""
    manifest = _make_manifest(pipeline_fingerprint="sha256:aaaa" + "0" * 60)
    html = render_html(manifest)
    # The full or a prefix of the fingerprint must appear
    assert "sha256:" in html


def test_render_html_includes_row_count() -> None:
    """render_html includes the row count value."""
    manifest = _make_manifest(row_counts={"customers": 250})
    html = render_html(manifest)
    assert "250" in html


def test_render_html_includes_timing_info() -> None:
    """render_html includes timing column/strategy names where available."""
    manifest = _make_manifest(
        timings=[
            {
                "strategy_type": "faker",
                "column": "email",
                "elapsed_ms": 42.0,
                "peak_memory_delta_kb": 8,
            }
        ]
    )
    html = render_html(manifest)
    assert "email" in html


def test_render_html_includes_warnings() -> None:
    """render_html includes warning details when present."""
    manifest = _make_manifest(
        warnings=[{"code": "low_distinct_ratio", "provider": "faker.name", "column": "email", "detail": {}}]
    )
    html = render_html(manifest)
    assert "low_distinct_ratio" in html


# ---------------------------------------------------------------------------
# R3: render_html is self-contained (no external CDN/JS)
# ---------------------------------------------------------------------------


def test_render_html_no_external_cdn() -> None:
    """render_html must not reference any external CDN URLs."""
    manifest = _make_manifest()
    html = render_html(manifest)
    # No http(s) URLs in href/src attributes
    assert "http://" not in html
    assert "https://" not in html


def test_render_html_no_external_script_src() -> None:
    """render_html must not include any <script src=...> tags."""
    manifest = _make_manifest()
    html = render_html(manifest)
    # Should have no script tag with src attribute
    lower = html.lower()
    assert "<script src" not in lower


def test_render_html_no_external_link_rel_stylesheet() -> None:
    """render_html must not link external stylesheets."""
    manifest = _make_manifest()
    html = render_html(manifest)
    # External stylesheet link would require http/https which we already block;
    # also block <link rel="stylesheet" href="..." pointing outside
    assert "//cdn" not in html.lower()


# ---------------------------------------------------------------------------
# R4: render_html includes omission disclaimer
# ---------------------------------------------------------------------------


def test_render_html_includes_omission_disclaimer() -> None:
    """render_html states what was intentionally excluded from the report."""
    manifest = _make_manifest()
    html = render_html(manifest)
    lower = html.lower()
    # Must mention that raw values are excluded
    assert "raw" in lower or "excluded" in lower or "evidence-safe" in lower


# ---------------------------------------------------------------------------
# R5-R6: render_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_produces_string() -> None:
    """render_markdown returns a non-empty string."""
    manifest = _make_manifest()
    md = render_markdown(manifest)
    assert isinstance(md, str)
    assert len(md) > 0


def test_render_markdown_includes_run_id() -> None:
    """render_markdown includes the run_id."""
    fixed_id = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    manifest = _make_manifest(run_id=fixed_id)
    md = render_markdown(manifest)
    assert fixed_id in md


def test_render_markdown_includes_pipeline_fingerprint() -> None:
    """render_markdown includes the pipeline fingerprint."""
    manifest = _make_manifest(pipeline_fingerprint="sha256:aaaa" + "0" * 60)
    md = render_markdown(manifest)
    assert "sha256:" in md


def test_render_markdown_includes_row_count() -> None:
    """render_markdown includes the row count."""
    manifest = _make_manifest(row_counts={"customers": 777})
    md = render_markdown(manifest)
    assert "777" in md


def test_render_markdown_includes_omission_disclaimer() -> None:
    """render_markdown states what was intentionally excluded."""
    manifest = _make_manifest()
    md = render_markdown(manifest)
    lower = md.lower()
    assert "raw" in lower or "excluded" in lower or "evidence-safe" in lower


# ---------------------------------------------------------------------------
# R14-R15: strategy names included; raw values never present
# ---------------------------------------------------------------------------


def test_render_html_includes_strategy_names() -> None:
    """render_html includes strategy names from the manifest."""
    manifest = _make_manifest(
        strategies=[{"table": "customers", "column": "email", "strategy": "faker"}]
    )
    html = render_html(manifest)
    assert "faker" in html
    assert "email" in html


def test_render_markdown_includes_strategy_names() -> None:
    """render_markdown includes strategy names from the manifest."""
    manifest = _make_manifest(
        strategies=[{"table": "orders", "column": "credit_card", "strategy": "redact"}]
    )
    md = render_markdown(manifest)
    assert "redact" in md
    assert "credit_card" in md


# ---------------------------------------------------------------------------
# R7: compare_manifests detects changed pipeline fingerprint
# ---------------------------------------------------------------------------


def test_compare_manifests_detects_changed_pipeline_fingerprint() -> None:
    """compare_manifests reports a pipeline fingerprint change."""
    old = _make_manifest(pipeline_fingerprint="sha256:" + "a" * 64)
    new = copy.deepcopy(old)
    new["pipeline_fingerprint"] = "sha256:" + "b" * 64

    result = compare_manifests(old, new)

    assert result["pipeline_fingerprint_changed"] is True


def test_compare_manifests_no_pipeline_change_when_same() -> None:
    """compare_manifests reports no pipeline change when fingerprints are equal."""
    old = _make_manifest(pipeline_fingerprint="sha256:" + "a" * 64)
    new = copy.deepcopy(old)

    result = compare_manifests(old, new)

    assert result["pipeline_fingerprint_changed"] is False


# ---------------------------------------------------------------------------
# R8: compare_manifests detects row-count delta
# ---------------------------------------------------------------------------


def test_compare_manifests_detects_row_count_delta() -> None:
    """compare_manifests reports a row count change."""
    old = _make_manifest(row_counts={"customers": 100})
    new = copy.deepcopy(old)
    new["row_counts"] = {"customers": 150}

    result = compare_manifests(old, new)

    deltas = result["row_count_deltas"]
    assert len(deltas) > 0
    delta_map = {d["table"]: d for d in deltas}
    assert "customers" in delta_map
    assert delta_map["customers"]["old"] == 100
    assert delta_map["customers"]["new"] == 150
    assert delta_map["customers"]["delta"] == 50


def test_compare_manifests_no_row_count_delta_when_same() -> None:
    """compare_manifests shows no row count deltas when counts are equal."""
    old = _make_manifest(row_counts={"customers": 100})
    new = copy.deepcopy(old)

    result = compare_manifests(old, new)

    assert result["row_count_deltas"] == []


# ---------------------------------------------------------------------------
# R9-R10: warnings added/removed
# ---------------------------------------------------------------------------


def test_compare_manifests_detects_warnings_added() -> None:
    """compare_manifests reports warnings present in new but not in old."""
    old = _make_manifest(warnings=[])
    new = copy.deepcopy(old)
    new["warnings"] = [{"code": "low_distinct_ratio", "provider": "faker.name", "column": "email", "detail": {}}]

    result = compare_manifests(old, new)

    assert len(result["warnings_added"]) > 0


def test_compare_manifests_detects_warnings_removed() -> None:
    """compare_manifests reports warnings present in old but not in new."""
    old = _make_manifest(
        warnings=[{"code": "low_distinct_ratio", "provider": "faker.name", "column": "email", "detail": {}}]
    )
    new = copy.deepcopy(old)
    new["warnings"] = []

    result = compare_manifests(old, new)

    assert len(result["warnings_removed"]) > 0


def test_compare_manifests_no_warning_changes_when_same() -> None:
    """compare_manifests shows no warning changes when both are identical."""
    warning = {"code": "low_distinct_ratio", "provider": "faker.name", "column": "email", "detail": {}}
    old = _make_manifest(warnings=[warning])
    new = copy.deepcopy(old)

    result = compare_manifests(old, new)

    assert result["warnings_added"] == []
    assert result["warnings_removed"] == []


# ---------------------------------------------------------------------------
# R11: compare_manifests no change when identical
# ---------------------------------------------------------------------------


def test_compare_manifests_no_change_when_identical() -> None:
    """compare_manifests reports any_change=False for identical manifests."""
    manifest = _make_manifest()
    new = copy.deepcopy(manifest)

    result = compare_manifests(manifest, new)

    assert result["any_change"] is False


# ---------------------------------------------------------------------------
# R12-R13: compare_manifests detects input/output fingerprint changes
# ---------------------------------------------------------------------------


def test_compare_manifests_detects_changed_input_fingerprint() -> None:
    """compare_manifests detects a changed input fingerprint."""
    old = _make_manifest(input_fp="sha256:" + "a" * 64)
    new = copy.deepcopy(old)
    new["input_fingerprints"]["customers"]["fingerprint"] = "sha256:" + "b" * 64

    result = compare_manifests(old, new)

    changed = result["input_fingerprint_changes"]["changed"]
    assert any(c["table"] == "customers" for c in changed)


def test_compare_manifests_detects_changed_output_fingerprint() -> None:
    """compare_manifests detects a changed output fingerprint."""
    old = _make_manifest(output_fp="sha256:" + "a" * 64)
    new = copy.deepcopy(old)
    new["output_fingerprints"]["customers"]["fingerprint"] = "sha256:" + "b" * 64

    result = compare_manifests(old, new)

    changed = result["output_fingerprint_changes"]["changed"]
    assert any(c["table"] == "customers" for c in changed)
