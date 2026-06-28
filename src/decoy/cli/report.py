"""``decoy report`` -- render, summarize, and compare local evidence manifests (SP-18).

Three subcommands operating on evidence manifests produced by
``decoy run --evidence-out <path>`` (SP-17, ``cli-local-1`` schema):

  render    -- Write an HTML or Markdown report to a file.
  summarize -- Print a concise Rich summary to the terminal.
  compare   -- Compare two manifests and report changes.

RAW-VALUE ISOLATION (Dennis review note, cli-first-capability-guide.md L534-538):

  Reports build from evidence-safe data only. The manifest already excludes
  raw row values (strategy names + fingerprints + metadata only), so rendering
  the manifest is safe by construction.

  This module accepts a manifest DICT and renders it. It does NOT:
    - Read source or output CSV files from disk.
    - Embed raw cell/row values in any report.
    - Render full STORM profiles or raw diagnostic values.

  What is intentionally excluded is stated in each report footer so reviewers
  know the omission is deliberate.

Deferred (not built here):
  - ``report show <run-id>`` -- needs the run-history store (SP-17b/catalog).
  - ``jobs list/show/watch`` -- needs run-history + live telemetry (SP-18b).
  - ``compare source.csv masked.csv`` -- data-level compare (SP-18b/19).
"""

from __future__ import annotations

import html as _html_mod
import json as _json
from pathlib import Path
from typing import Any

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.theme import code, error, hint, info, success, warn

# ---------------------------------------------------------------------------
# Typer app registration
# ---------------------------------------------------------------------------

report_app = typer.Typer(
    name="report",
    help=(
        "Render, summarize, and compare local evidence manifests. "
        "Operates on evidence JSON files produced by `decoy run --evidence-out`."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Manifest loader (shared)
# ---------------------------------------------------------------------------


def _load_manifest(path: Path, state: OutputState, command: str) -> dict[str, Any]:
    """Load and parse a manifest file. Exit with EXIT_USAGE on any error."""
    if not path.exists():
        msg = f"evidence file not found: {path}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("hint:"),
                "produce an evidence file with",
                code("decoy run pipeline.yaml --evidence-out evidence.json"),
            )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        raw = path.read_text(encoding="utf-8")
        manifest = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        msg = f"could not parse {path.name} as JSON: {exc.msg}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)
    except OSError as exc:
        msg = f"could not read {path}: {exc}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    return manifest


# ---------------------------------------------------------------------------
# Pure renderer: HTML
# ---------------------------------------------------------------------------

_HTML_CSS = """\
body { font-family: monospace; max-width: 900px; margin: 2em auto; background: #111; color: #e0e0e0; }
h1 { color: #00d4aa; border-bottom: 1px solid #333; padding-bottom: 0.3em; }
h2 { color: #00d4aa; margin-top: 1.5em; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0 1em 0; }
th { background: #1e1e1e; color: #00d4aa; text-align: left; padding: 0.4em 0.8em; border: 1px solid #333; }
td { padding: 0.4em 0.8em; border: 1px solid #333; word-break: break-all; }
tr:nth-child(even) td { background: #1a1a1a; }
.badge-ok { color: #00d4aa; }
.badge-warn { color: #f0a500; }
.badge-none { color: #666; }
.fp { font-size: 0.85em; color: #aaa; }
footer { margin-top: 2em; border-top: 1px solid #333; padding-top: 0.8em; font-size: 0.85em; color: #666; }
"""


def _esc(value: Any) -> str:
    """HTML-escape a value for safe embedding in attributes and text."""
    return _html_mod.escape(str(value) if value is not None else "")


def render_html(manifest: dict[str, Any]) -> str:
    """Render a manifest dict to a self-contained, offline HTML report.

    EVIDENCE-SAFE: builds entirely from the manifest dict. Does NOT read any
    source CSV, output CSV, or pipeline YAML file from disk. The manifest
    itself never contains raw row values (see build_manifest in evidence.py).

    Returns a complete HTML document as a string.
    """
    run_id = _esc(manifest.get("run_id", "?"))
    run_ts = _esc(manifest.get("run_timestamp", "?"))
    schema_v = _esc(manifest.get("schema_version", "?"))
    producer = _esc(manifest.get("producer", "?"))
    cli_v = _esc(manifest.get("cli_version", "?"))
    eng_v = _esc(manifest.get("engine_version", "?"))
    pipeline_path = _esc(manifest.get("pipeline_path", "?"))
    pipeline_fp = manifest.get("pipeline_fingerprint") or ""
    pipeline_fp_esc = _esc(pipeline_fp)
    key_label = _esc(manifest.get("key_label") or "(none)")

    warnings_list: list[Any] = manifest.get("warnings") or []
    timings_list: list[Any] = manifest.get("timings") or []
    strategies_list: list[Any] = manifest.get("strategies") or []
    input_fps: dict[str, Any] = manifest.get("input_fingerprints") or {}
    output_fps: dict[str, Any] = manifest.get("output_fingerprints") or {}
    row_counts: dict[str, Any] = manifest.get("row_counts") or {}

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang=\"en\">")
    parts.append("<head>")
    parts.append("<meta charset=\"UTF-8\">")
    parts.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    parts.append("<title>Decoy Evidence Report</title>")
    parts.append(f"<style>{_HTML_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<h1>Decoy Evidence Report</h1>")

    # --- Run Summary ---
    parts.append("<h2>Run Summary</h2>")
    parts.append("<table>")
    parts.append("<tr><th>Field</th><th>Value</th></tr>")
    for label, val in [
        ("Schema Version", schema_v),
        ("Producer", producer),
        ("Run ID", run_id),
        ("Run Timestamp", run_ts),
        ("CLI Version", cli_v),
        ("Engine Version", eng_v),
        ("Key Label", key_label),
    ]:
        parts.append(f"<tr><td>{label}</td><td>{val}</td></tr>")
    parts.append("</table>")

    # --- Pipeline Identity ---
    parts.append("<h2>Pipeline Identity</h2>")
    parts.append("<table>")
    parts.append("<tr><th>Field</th><th>Value</th></tr>")
    parts.append(f"<tr><td>Pipeline Path</td><td>{pipeline_path}</td></tr>")
    parts.append(
        f"<tr><td>Pipeline Fingerprint</td><td class=\"fp\">{pipeline_fp_esc}</td></tr>"
    )
    parts.append("</table>")

    # --- Input Fingerprints ---
    if input_fps:
        parts.append("<h2>Input Fingerprints</h2>")
        parts.append("<table>")
        parts.append("<tr><th>Table</th><th>Path</th><th>Fingerprint</th><th>Method</th><th>Size (bytes)</th></tr>")
        for tname, info_val in input_fps.items():
            if not isinstance(info_val, dict):
                continue
            fp = _esc(info_val.get("fingerprint") or "(none)")
            method = _esc(info_val.get("fingerprint_method") or "?")
            size = _esc(info_val.get("size_bytes") or "?")
            path_v = _esc(info_val.get("path") or "?")
            parts.append(
                f"<tr><td>{_esc(tname)}</td><td>{path_v}</td>"
                f"<td class=\"fp\">{fp}</td><td>{method}</td><td>{size}</td></tr>"
            )
        parts.append("</table>")

    # --- Output Fingerprints ---
    if output_fps:
        parts.append("<h2>Output Fingerprints</h2>")
        parts.append("<table>")
        parts.append("<tr><th>Table</th><th>Path</th><th>Fingerprint</th><th>Method</th><th>Size (bytes)</th></tr>")
        for tname, info_val in output_fps.items():
            if not isinstance(info_val, dict):
                continue
            fp = _esc(info_val.get("fingerprint") or "(none)")
            method = _esc(info_val.get("fingerprint_method") or "?")
            size = _esc(info_val.get("size_bytes") or "?")
            path_v = _esc(info_val.get("path") or "?")
            parts.append(
                f"<tr><td>{_esc(tname)}</td><td>{path_v}</td>"
                f"<td class=\"fp\">{fp}</td><td>{method}</td><td>{size}</td></tr>"
            )
        parts.append("</table>")

    # --- Row Counts ---
    if row_counts:
        parts.append("<h2>Row Counts</h2>")
        parts.append("<table>")
        parts.append("<tr><th>Table</th><th>Rows</th></tr>")
        for tname, count in row_counts.items():
            parts.append(f"<tr><td>{_esc(tname)}</td><td>{_esc(count)}</td></tr>")
        parts.append("</table>")

    # --- Masking Strategies ---
    if strategies_list:
        parts.append("<h2>Masking Strategies</h2>")
        parts.append("<table>")
        parts.append("<tr><th>Table</th><th>Column</th><th>Strategy</th></tr>")
        for s in strategies_list:
            if not isinstance(s, dict):
                continue
            parts.append(
                f"<tr><td>{_esc(s.get('table', '?'))}</td>"
                f"<td>{_esc(s.get('column', '?'))}</td>"
                f"<td>{_esc(s.get('strategy', '?'))}</td></tr>"
            )
        parts.append("</table>")

    # --- Node Timings ---
    if timings_list:
        parts.append("<h2>Node Timings</h2>")
        parts.append("<table>")
        parts.append(
            "<tr><th>Column</th><th>Strategy</th><th>Elapsed (ms)</th><th>Peak Mem Delta (KB)</th></tr>"
        )
        for t in timings_list:
            if not isinstance(t, dict):
                continue
            parts.append(
                f"<tr><td>{_esc(t.get('column', '?'))}</td>"
                f"<td>{_esc(t.get('strategy_type', '?'))}</td>"
                f"<td>{_esc(t.get('elapsed_ms', '?'))}</td>"
                f"<td>{_esc(t.get('peak_memory_delta_kb', '?'))}</td></tr>"
            )
        parts.append("</table>")

    # --- Warnings ---
    warn_count = len(warnings_list)
    parts.append("<h2>Warnings</h2>")
    if warn_count == 0:
        parts.append("<p class=\"badge-ok\">No warnings recorded.</p>")
    else:
        parts.append(f"<p class=\"badge-warn\">{_esc(warn_count)} warning(s) recorded.</p>")
        parts.append("<table>")
        parts.append("<tr><th>#</th><th>Code</th><th>Provider</th><th>Column</th><th>Detail</th></tr>")
        for i, w in enumerate(warnings_list, start=1):
            if isinstance(w, dict):
                wcode = _esc(w.get("code", "?"))
                wprov = _esc(w.get("provider", "?"))
                wcol = _esc(w.get("column", "(none)"))
                wdet = _esc(_json.dumps(w.get("detail") or {}))
                parts.append(
                    f"<tr><td>{i}</td><td>{wcode}</td><td>{wprov}</td>"
                    f"<td>{wcol}</td><td>{wdet}</td></tr>"
                )
            else:
                parts.append(f"<tr><td>{i}</td><td colspan=\"4\">{_esc(w)}</td></tr>")
        parts.append("</table>")

    # --- Footer / omission disclaimer ---
    parts.append("<footer>")
    parts.append(
        "<p>Report generated from evidence-safe data only. "
        "Raw row/cell values are intentionally excluded from this report. "
        "The evidence manifest records strategy names, fingerprints, and metadata only. "
        "Data correctness and masking quality are not verified by this report.</p>"
    )
    parts.append("</footer>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Pure renderer: Markdown
# ---------------------------------------------------------------------------


def render_markdown(manifest: dict[str, Any]) -> str:
    """Render a manifest dict to a plain Markdown report.

    EVIDENCE-SAFE: builds entirely from the manifest dict. Does NOT read any
    source CSV, output CSV, or pipeline YAML file from disk.

    Returns a Markdown string suitable for writing to a .md file.
    """
    run_id = manifest.get("run_id", "?")
    run_ts = manifest.get("run_timestamp", "?")
    schema_v = manifest.get("schema_version", "?")
    producer = manifest.get("producer", "?")
    cli_v = manifest.get("cli_version", "?")
    eng_v = manifest.get("engine_version", "?")
    pipeline_path = manifest.get("pipeline_path", "?")
    pipeline_fp = manifest.get("pipeline_fingerprint") or "(none)"
    key_label = manifest.get("key_label") or "(none)"

    warnings_list: list[Any] = manifest.get("warnings") or []
    timings_list: list[Any] = manifest.get("timings") or []
    strategies_list: list[Any] = manifest.get("strategies") or []
    input_fps: dict[str, Any] = manifest.get("input_fingerprints") or {}
    output_fps: dict[str, Any] = manifest.get("output_fingerprints") or {}
    row_counts: dict[str, Any] = manifest.get("row_counts") or {}

    lines: list[str] = []
    lines.append("# Decoy Evidence Report")
    lines.append("")

    # --- Run Summary ---
    lines.append("## Run Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for label, val in [
        ("Schema Version", schema_v),
        ("Producer", producer),
        ("Run ID", run_id),
        ("Run Timestamp", run_ts),
        ("CLI Version", cli_v),
        ("Engine Version", eng_v),
        ("Key Label", key_label),
    ]:
        lines.append(f"| {label} | {val} |")
    lines.append("")

    # --- Pipeline Identity ---
    lines.append("## Pipeline Identity")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Pipeline Path | {pipeline_path} |")
    lines.append(f"| Pipeline Fingerprint | `{pipeline_fp}` |")
    lines.append("")

    # --- Input Fingerprints ---
    if input_fps:
        lines.append("## Input Fingerprints")
        lines.append("")
        lines.append("| Table | Path | Fingerprint | Method | Size (bytes) |")
        lines.append("|---|---|---|---|---|")
        for tname, info_val in input_fps.items():
            if not isinstance(info_val, dict):
                continue
            fp = info_val.get("fingerprint") or "(none)"
            method = info_val.get("fingerprint_method") or "?"
            size = str(info_val.get("size_bytes") or "?")
            path_v = info_val.get("path") or "?"
            lines.append(f"| {tname} | {path_v} | `{fp}` | {method} | {size} |")
        lines.append("")

    # --- Output Fingerprints ---
    if output_fps:
        lines.append("## Output Fingerprints")
        lines.append("")
        lines.append("| Table | Path | Fingerprint | Method | Size (bytes) |")
        lines.append("|---|---|---|---|---|")
        for tname, info_val in output_fps.items():
            if not isinstance(info_val, dict):
                continue
            fp = info_val.get("fingerprint") or "(none)"
            method = info_val.get("fingerprint_method") or "?"
            size = str(info_val.get("size_bytes") or "?")
            path_v = info_val.get("path") or "?"
            lines.append(f"| {tname} | {path_v} | `{fp}` | {method} | {size} |")
        lines.append("")

    # --- Row Counts ---
    if row_counts:
        lines.append("## Row Counts")
        lines.append("")
        lines.append("| Table | Rows |")
        lines.append("|---|---|")
        for tname, count in row_counts.items():
            lines.append(f"| {tname} | {count} |")
        lines.append("")

    # --- Masking Strategies ---
    if strategies_list:
        lines.append("## Masking Strategies")
        lines.append("")
        lines.append("| Table | Column | Strategy |")
        lines.append("|---|---|---|")
        for s in strategies_list:
            if not isinstance(s, dict):
                continue
            lines.append(
                f"| {s.get('table', '?')} | {s.get('column', '?')} | {s.get('strategy', '?')} |"
            )
        lines.append("")

    # --- Node Timings ---
    if timings_list:
        lines.append("## Node Timings")
        lines.append("")
        lines.append("| Column | Strategy | Elapsed (ms) | Peak Mem Delta (KB) |")
        lines.append("|---|---|---|---|")
        for t in timings_list:
            if not isinstance(t, dict):
                continue
            lines.append(
                f"| {t.get('column', '?')} | {t.get('strategy_type', '?')} "
                f"| {t.get('elapsed_ms', '?')} | {t.get('peak_memory_delta_kb', '?')} |"
            )
        lines.append("")

    # --- Warnings ---
    warn_count = len(warnings_list)
    lines.append("## Warnings")
    lines.append("")
    if warn_count == 0:
        lines.append("No warnings recorded.")
    else:
        lines.append(f"{warn_count} warning(s) recorded.")
        lines.append("")
        lines.append("| # | Code | Provider | Column | Detail |")
        lines.append("|---|---|---|---|---|")
        for i, w in enumerate(warnings_list, start=1):
            if isinstance(w, dict):
                wcode = w.get("code", "?")
                wprov = w.get("provider", "?")
                wcol = w.get("column") or "(none)"
                wdet = _json.dumps(w.get("detail") or {})
                lines.append(f"| {i} | {wcode} | {wprov} | {wcol} | {wdet} |")
            else:
                lines.append(f"| {i} | {w} | | | |")
    lines.append("")

    # --- Footer / omission disclaimer ---
    lines.append("---")
    lines.append("")
    lines.append(
        "*Report generated from evidence-safe data only. "
        "Raw row/cell values are intentionally excluded. "
        "The evidence manifest records strategy names, fingerprints, and metadata only. "
        "Data correctness and masking quality are not verified by this report.*"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pure helper: compare_manifests
# ---------------------------------------------------------------------------


def _warning_key(w: Any) -> str:
    """Produce a stable string key for a warning entry (for set-diff comparison)."""
    if isinstance(w, dict):
        return _json.dumps(w, sort_keys=True)
    return str(w)


def compare_manifests(
    old: dict[str, Any], new: dict[str, Any]
) -> dict[str, Any]:
    """Compare two evidence manifests and return a structured diff.

    EVIDENCE-SAFE: operates entirely on manifest dicts. Does NOT read any
    files from disk.

    Returns a dict with:
      pipeline_fingerprint_changed   bool
      old_pipeline_fingerprint       str | None
      new_pipeline_fingerprint       str | None
      input_fingerprint_changes      dict with "changed", "added", "removed" lists
      output_fingerprint_changes     dict with "changed", "added", "removed" lists
      row_count_deltas               list of {"table", "old", "new", "delta"}
      warnings_added                 list (warnings in new but not old)
      warnings_removed               list (warnings in old but not in new)
      any_change                     bool
    """
    old_pf = old.get("pipeline_fingerprint")
    new_pf = new.get("pipeline_fingerprint")
    pipeline_fp_changed = old_pf != new_pf

    # --- Fingerprint helpers ---
    def _fp_changes(
        old_fps: dict[str, Any], new_fps: dict[str, Any]
    ) -> dict[str, list[Any]]:
        changed: list[dict[str, Any]] = []
        added: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        all_tables = set(old_fps) | set(new_fps)
        for tname in sorted(all_tables):
            old_info = old_fps.get(tname) if isinstance(old_fps.get(tname), dict) else {}
            new_info = new_fps.get(tname) if isinstance(new_fps.get(tname), dict) else {}
            old_fp = (old_info or {}).get("fingerprint") if old_info else None
            new_fp = (new_info or {}).get("fingerprint") if new_info else None

            if tname not in old_fps:
                added.append({"table": tname, "fingerprint": new_fp})
            elif tname not in new_fps:
                removed.append({"table": tname, "fingerprint": old_fp})
            elif old_fp != new_fp:
                changed.append({"table": tname, "old": old_fp, "new": new_fp})
        return {"changed": changed, "added": added, "removed": removed}

    old_in = old.get("input_fingerprints") or {}
    new_in = new.get("input_fingerprints") or {}
    input_changes = _fp_changes(old_in, new_in)

    old_out = old.get("output_fingerprints") or {}
    new_out = new.get("output_fingerprints") or {}
    output_changes = _fp_changes(old_out, new_out)

    # --- Row count deltas ---
    old_rc: dict[str, Any] = old.get("row_counts") or {}
    new_rc: dict[str, Any] = new.get("row_counts") or {}
    all_tables = set(old_rc) | set(new_rc)
    row_count_deltas: list[dict[str, Any]] = []
    for tname in sorted(all_tables):
        old_count = old_rc.get(tname)
        new_count = new_rc.get(tname)
        if old_count != new_count:
            try:
                delta = int(new_count or 0) - int(old_count or 0)
            except (TypeError, ValueError):
                delta = None
            row_count_deltas.append(
                {"table": tname, "old": old_count, "new": new_count, "delta": delta}
            )

    # --- Warnings set-diff ---
    old_warn_keys = {_warning_key(w) for w in (old.get("warnings") or [])}
    new_warn_keys = {_warning_key(w) for w in (new.get("warnings") or [])}

    warnings_added = [
        w for w in (new.get("warnings") or []) if _warning_key(w) not in old_warn_keys
    ]
    warnings_removed = [
        w for w in (old.get("warnings") or []) if _warning_key(w) not in new_warn_keys
    ]

    # --- any_change aggregation ---
    in_has_change = bool(
        input_changes["changed"] or input_changes["added"] or input_changes["removed"]
    )
    out_has_change = bool(
        output_changes["changed"] or output_changes["added"] or output_changes["removed"]
    )
    any_change = bool(
        pipeline_fp_changed
        or in_has_change
        or out_has_change
        or row_count_deltas
        or warnings_added
        or warnings_removed
    )

    return {
        "pipeline_fingerprint_changed": pipeline_fp_changed,
        "old_pipeline_fingerprint": old_pf,
        "new_pipeline_fingerprint": new_pf,
        "input_fingerprint_changes": input_changes,
        "output_fingerprint_changes": output_changes,
        "row_count_deltas": row_count_deltas,
        "warnings_added": warnings_added,
        "warnings_removed": warnings_removed,
        "any_change": any_change,
    }


# ---------------------------------------------------------------------------
# CLI: report render
# ---------------------------------------------------------------------------

_RENDER_EPILOG = """\
Examples:

  decoy report render evidence.json --out report.html
    Render the manifest as a self-contained offline HTML report.

  decoy report render evidence.json --format markdown --out report.md
    Render the manifest as a plain Markdown report.

What the report includes:
  Run summary, pipeline identity (fingerprint), input/output fingerprints,
  row counts, masking strategies (names only), node timings, and warnings.

What the report intentionally excludes:
  Raw row values, PII samples, STORM profile internals, diagnostic values.
  The evidence manifest records strategy names and fingerprints only; the
  report renders that safe subset.

See also: decoy report summarize, decoy report compare, decoy evidence show.
"""


def _render(
    evidence_file: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to a local evidence manifest JSON (produced by decoy run --evidence-out).",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output file path (e.g. report.html or report.md).",
    ),
    format_: str = typer.Option(
        "html",
        "--format",
        help="Output format: 'html' (default) or 'markdown'.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Render an evidence manifest to an HTML or Markdown report file.

    The report is built from the manifest only (evidence-safe). Raw row
    values, PII, and STORM profile internals are never included.

    HTML output is self-contained and offline-capable (no CDN/external JS).
    Markdown output is plain text.
    """
    state = setup_output(False, quiet, verbose)
    manifest = _load_manifest(evidence_file, state, "report render")

    fmt = format_.lower().strip()
    if fmt not in ("html", "markdown", "md"):
        state.err_console.print(
            error("error:"),
            f"unknown format {format_!r}; use 'html' or 'markdown'.",
        )
        raise typer.Exit(code=EXIT_USAGE)

    if fmt in ("markdown", "md"):
        content = render_markdown(manifest)
    else:
        content = render_html(manifest)

    try:
        out.write_text(content, encoding="utf-8")
    except OSError as exc:
        state.err_console.print(error("error:"), f"could not write {out}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    if state.mode is not OutputMode.quiet:
        fmt_label = "Markdown" if fmt in ("markdown", "md") else "HTML"
        state.console.print(
            success("ok"),
            f"{fmt_label} report written to",
            code(str(out)),
        )
        state.console.print(
            " ",
            hint("note:"),
            "report contains evidence-safe data only (no raw values).",
        )


# ---------------------------------------------------------------------------
# CLI: report summarize
# ---------------------------------------------------------------------------

_SUMMARIZE_EPILOG = """\
Examples:

  decoy report summarize evidence.json
    Print a concise summary of the evidence manifest to the terminal.

What summarize shows:
  Run ID, timestamp, CLI/engine versions, pipeline fingerprint (prefix),
  input/output fingerprint counts, row counts per table, and warning count.

See also: decoy report render, decoy evidence show.
"""


def _summarize(
    evidence_file: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to a local evidence manifest JSON.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Print a concise terminal summary of a local evidence manifest.

    Renders key fields from the manifest in a Rich card: run metadata,
    pipeline fingerprint, input/output counts, row counts, and warnings.
    Read-only; never modifies files.
    """
    from decoy.ui.card import render_card
    from decoy.ui.table import make_table

    state = setup_output(False, quiet, verbose)
    manifest = _load_manifest(evidence_file, state, "report summarize")

    if state.mode is OutputMode.quiet:
        return

    run_id = manifest.get("run_id", "?")
    run_ts = manifest.get("run_timestamp", "?")
    cli_v = manifest.get("cli_version", "?")
    eng_v = manifest.get("engine_version", "?")
    schema_v = manifest.get("schema_version", "?")
    producer = manifest.get("producer", "?")
    pipeline_fp = manifest.get("pipeline_fingerprint") or ""
    warnings_list = manifest.get("warnings") or []
    input_fps = manifest.get("input_fingerprints") or {}
    output_fps = manifest.get("output_fingerprints") or {}
    row_counts: dict[str, Any] = manifest.get("row_counts") or {}

    fp_display = (pipeline_fp[:23] + "...") if len(pipeline_fp) > 23 else pipeline_fp

    facts: list[tuple[str, str]] = [
        ("Schema version", schema_v),
        ("Producer", producer),
        ("Run ID", (run_id[:16] + "...") if len(run_id) > 16 else run_id),
        ("Run timestamp", run_ts),
        ("CLI version", cli_v),
        ("Engine version", eng_v),
        ("Pipeline fingerprint", fp_display or "(none)"),
        ("Input tables", str(len(input_fps))),
        ("Output tables", str(len(output_fps))),
        ("Warnings", str(len(warnings_list))),
    ]

    render_card(
        state,
        command="decoy report summarize",
        facts=facts,
        next_hint=f"decoy report render {evidence_file} --out report.html",
        status="warn" if warnings_list else "ok",
    )

    # Row counts table
    if row_counts:
        t = make_table("Table", "Rows", title="Row counts")
        for tname, count in row_counts.items():
            t.add_row(str(tname), str(count))
        state.console.print(t)

    if warnings_list:
        state.err_console.print(
            warn("warning:"),
            f"{len(warnings_list)} warning(s) in manifest -- "
            "run `decoy evidence show` for details.",
        )


# ---------------------------------------------------------------------------
# CLI: report compare
# ---------------------------------------------------------------------------

_COMPARE_EPILOG = """\
Examples:

  decoy report compare old-evidence.json new-evidence.json
    Compare two evidence manifests and show which fingerprints changed,
    row-count deltas, and warnings added or removed.

  decoy report compare old-evidence.json new-evidence.json --json
    Emit structured JSON suitable for scripting.

What compare checks:
  - Pipeline fingerprint change.
  - Per-table input fingerprint changes (added/removed/changed).
  - Per-table output fingerprint changes (added/removed/changed).
  - Row count deltas per table.
  - Warnings added or removed.

What compare does NOT check:
  - Data correctness or masking quality.
  - Platform audit logs or schedule history.

Scope: MANIFEST-vs-MANIFEST only. Data-level compare (source.csv vs masked.csv)
is deferred to SP-18b/19.

See also: decoy report summarize, decoy evidence verify.
"""


def _compare(
    old_evidence: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to the older evidence manifest JSON.",
    ),
    new_evidence: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to the newer evidence manifest JSON.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit structured JSON instead of human-readable output.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Compare two evidence manifests and report what changed between runs.

    Detects changes in pipeline fingerprint, per-table input/output
    fingerprints, row counts, and warnings. MANIFEST-vs-MANIFEST only --
    does not read source/output CSV data files.

    Exits 0 in both change and no-change cases. Use --json for scripting.
    """
    state = setup_output(json_, quiet, verbose)
    old_manifest = _load_manifest(old_evidence, state, "report compare")
    new_manifest = _load_manifest(new_evidence, state, "report compare")

    diff = compare_manifests(old_manifest, new_manifest)

    if state.mode is OutputMode.json:
        payload = {
            "command": "report compare",
            "status": "ok",
            "old_evidence": str(old_evidence),
            "new_evidence": str(new_evidence),
        }
        payload.update(diff)
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    from decoy.ui.table import make_table

    any_change = diff["any_change"]

    if not any_change:
        state.console.print(
            success("ok"),
            "no changes detected between the two evidence manifests.",
        )
        state.console.print(
            " ",
            hint("note:"),
            "pipeline fingerprint, input/output fingerprints, row counts, "
            "and warnings are identical.",
        )
        return

    state.console.print(
        warn("changes detected"),
        "between",
        code(str(old_evidence)),
        "and",
        code(str(new_evidence)),
    )
    state.console.print("")

    # Pipeline fingerprint
    if diff["pipeline_fingerprint_changed"]:
        state.console.print(warn("Pipeline fingerprint changed:"))
        state.console.print(
            "  old:", code(_fp_short(diff["old_pipeline_fingerprint"]))
        )
        state.console.print(
            "  new:", code(_fp_short(diff["new_pipeline_fingerprint"]))
        )
        state.console.print("")

    # Input fingerprints
    in_ch = diff["input_fingerprint_changes"]
    if in_ch["changed"] or in_ch["added"] or in_ch["removed"]:
        t = make_table("Table", "Change", "Old Fingerprint", "New Fingerprint", title="Input fingerprints")
        for c in in_ch["changed"]:
            t.add_row(c["table"], "changed", _fp_short(c["old"]), _fp_short(c["new"]))
        for a in in_ch["added"]:
            t.add_row(a["table"], "added", "(none)", _fp_short(a["fingerprint"]))
        for r in in_ch["removed"]:
            t.add_row(r["table"], "removed", _fp_short(r["fingerprint"]), "(none)")
        state.console.print(t)

    # Output fingerprints
    out_ch = diff["output_fingerprint_changes"]
    if out_ch["changed"] or out_ch["added"] or out_ch["removed"]:
        t = make_table("Table", "Change", "Old Fingerprint", "New Fingerprint", title="Output fingerprints")
        for c in out_ch["changed"]:
            t.add_row(c["table"], "changed", _fp_short(c["old"]), _fp_short(c["new"]))
        for a in out_ch["added"]:
            t.add_row(a["table"], "added", "(none)", _fp_short(a["fingerprint"]))
        for r in out_ch["removed"]:
            t.add_row(r["table"], "removed", _fp_short(r["fingerprint"]), "(none)")
        state.console.print(t)

    # Row count deltas
    if diff["row_count_deltas"]:
        t = make_table("Table", "Old", "New", "Delta", title="Row count deltas")
        for d in diff["row_count_deltas"]:
            delta_str = str(d["delta"]) if d["delta"] is not None else "?"
            if isinstance(d["delta"], int) and d["delta"] > 0:
                delta_str = f"+{delta_str}"
            t.add_row(d["table"], str(d["old"]), str(d["new"]), delta_str)
        state.console.print(t)

    # Warnings diff
    if diff["warnings_added"]:
        state.console.print(warn(f"{len(diff['warnings_added'])} warning(s) added:"))
        for w in diff["warnings_added"]:
            if isinstance(w, dict):
                state.console.print(
                    "  +",
                    code(w.get("code", "?")),
                    info(f"col={w.get('column') or '(none)'}"),
                )
            else:
                state.console.print("  +", code(str(w)))

    if diff["warnings_removed"]:
        state.console.print(success(f"{len(diff['warnings_removed'])} warning(s) removed:"))
        for w in diff["warnings_removed"]:
            if isinstance(w, dict):
                state.console.print(
                    "  -",
                    code(w.get("code", "?")),
                    info(f"col={w.get('column') or '(none)'}"),
                )
            else:
                state.console.print("  -", code(str(w)))


def _fp_short(fp: str | None) -> str:
    """Return a shortened fingerprint for display (prefix + ellipsis)."""
    if not fp:
        return "(none)"
    return (fp[:23] + "...") if len(fp) > 23 else fp


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------

report_app.command(name="render", epilog=_RENDER_EPILOG)(_render)
report_app.command(name="summarize", epilog=_SUMMARIZE_EPILOG)(_summarize)
report_app.command(name="compare", epilog=_COMPARE_EPILOG)(_compare)

# Public exports
__all__ = [
    "compare_manifests",
    "render_html",
    "render_markdown",
    "report_app",
]
