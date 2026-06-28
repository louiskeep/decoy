"""Raw-value isolation sentry for ``decoy report`` (SP-18).

Dennis review note (cli-first-capability-guide.md L534-538):
  Reporting must build from evidence-safe data only. Do not render full STORM
  profiles or raw diagnostic values into HTML/Markdown by default.

This sentry verifies that the renderers CANNOT include raw data values
even if a non-manifest source file containing PII sits in the same directory.

The test:
1. Builds a valid manifest dict (no raw values by construction).
2. Places a sentinel string ("SENTRY_RAW_VALUE_ZZZZZ") in a sibling file
   in the same tmp directory -- simulating a real source or output CSV.
3. Calls render_html and render_markdown with the manifest ONLY.
4. Asserts the sentinel NEVER appears in either rendered report.

Why: the renderers accept a manifest dict, not a directory. They cannot
accidentally slurp up sibling files. This test proves that invariant holds.

If this test fails it means a renderer is reading files from the filesystem
by path -- which would break the evidence-safe contract.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from decoy.cli.report import render_html, render_markdown

# The sentinel must not be a real PII value; it just must be unique enough
# that we are certain it cannot appear in a generated report by coincidence.
_SENTINEL = "SENTRY_RAW_VALUE_ZZZZZ_" + "X" * 20


def _make_manifest_with_file_paths(tmp_path: Path) -> dict[str, Any]:
    """Make a manifest whose file paths point into tmp_path (sentinel lives there too)."""
    return {
        "schema_version": "cli-local-1",
        "producer": "decoy-cli",
        "run_id": str(uuid.uuid4()),
        "run_timestamp": "2026-06-28T10:00:00+00:00",
        "cli_version": "0.5.0",
        "engine_version": "0.4.0",
        "pipeline_path": str(tmp_path / "pipeline.yaml"),
        "pipeline_fingerprint": "sha256:" + "a" * 64,
        "input_fingerprints": {
            "customers": {
                "path": str(tmp_path / "source.csv"),
                "fingerprint": "sha256:" + "b" * 64,
                "fingerprint_method": "full",
                "size_bytes": 512,
            }
        },
        "output_fingerprints": {
            "customers": {
                "path": str(tmp_path / "masked.csv"),
                "fingerprint": "sha256:" + "c" * 64,
                "fingerprint_method": "full",
                "size_bytes": 512,
            }
        },
        "row_counts": {"customers": 50},
        "key_label": None,
        "warnings": [],
        "timings": [],
        "strategies": [{"table": "customers", "column": "email", "strategy": "faker"}],
        "manifest_hash": "sha256:" + "d" * 64,
    }


def test_render_html_does_not_read_sibling_files(tmp_path: Path) -> None:
    """render_html must not include the sentinel from a sibling source file.

    Even though the manifest records paths that point into tmp_path, the
    renderer must not read those files. The sentinel appears only in the
    sibling CSV, never in the manifest dict.
    """
    # Plant the sentinel in a file adjacent to the evidence paths
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    masked_csv = tmp_path / "masked.csv"
    masked_csv.write_text("email\nfake@example.com\n", encoding="utf-8")

    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(f"# pipeline\n# {_SENTINEL}\n", encoding="utf-8")

    manifest = _make_manifest_with_file_paths(tmp_path)

    html = render_html(manifest)

    assert _SENTINEL not in html, (
        f"render_html leaked the sentinel '{_SENTINEL}' into the HTML report. "
        "The renderer must build from the manifest dict only -- it must not read "
        "source/output CSV files or any other on-disk data."
    )


def test_render_markdown_does_not_read_sibling_files(tmp_path: Path) -> None:
    """render_markdown must not include the sentinel from a sibling source file."""
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    masked_csv = tmp_path / "masked.csv"
    masked_csv.write_text("email\nfake@example.com\n", encoding="utf-8")

    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(f"# {_SENTINEL}\n", encoding="utf-8")

    manifest = _make_manifest_with_file_paths(tmp_path)

    md = render_markdown(manifest)

    assert _SENTINEL not in md, (
        f"render_markdown leaked the sentinel '{_SENTINEL}' into the Markdown report. "
        "The renderer must build from the manifest dict only."
    )


def test_sentinel_actually_present_in_sibling_file(tmp_path: Path) -> None:
    """Negative control: confirm the sentinel IS in the sibling file.

    This ensures the sentry cannot be defeated by the sentinel simply never
    being written. If this test fails, the sentry setup is broken.
    """
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    content = source_csv.read_text(encoding="utf-8")
    assert _SENTINEL in content, "Setup error: sentinel not written to sibling file."
