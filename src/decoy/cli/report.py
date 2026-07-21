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

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
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
is not yet supported.

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
# Data-level diff helper: compare_data
# ---------------------------------------------------------------------------


def _column_profile(df: "Any") -> dict[str, dict[str, Any]]:
    """Build a per-column summary profile from a pandas DataFrame.

    Returns a dict keyed by column name with:
      - dtype_kind: pandas dtype kind char ('i', 'f', 'u', 'O', 'M', 'b', ...)
      - null_count: int
      - unique_count: int

    Methodology: pandas.Series.nunique() and .isnull().sum() for column-level
    null/cardinality counts. No novel statistical method is used.

    EVIDENCE-SAFE: aggregate counts only -- no raw cell values are returned.
    """
    profile: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        series = df[col]
        kind = series.dtype.kind
        null_count = int(series.isnull().sum())
        unique_count = int(series.nunique(dropna=True))
        profile[col] = {
            "dtype_kind": kind,
            "null_count": null_count,
            "unique_count": unique_count,
        }
    return profile


def compare_data(
    output_fps_a: dict[str, Any],
    output_fps_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare output data files from two runs at the data level.

    Accepts the `output_fingerprints` dicts from two evidence manifests.
    Each dict is keyed by table name and has a `path` field pointing to
    the output file (CSV or Parquet).

    Returns a structured dict with:
      any_data_change  bool
      table_deltas     list of per-table dicts with:
        table             str
        row_count_a       int or None
        row_count_b       int or None
        row_count_delta   int or None
        columns_added     list[str] -- columns in B but not A
        columns_removed   list[str] -- columns in A but not B
        column_deltas     list of per-column dicts with:
          column          str
          null_count_delta  int or None
          unique_count_delta int or None
          dtype_kind_a    str or None
          dtype_kind_b    str or None
          dtype_changed   bool
      missing_files      list[str] -- paths that could not be found

    Methodology: pandas.Series.nunique() and .isnull().sum() for column-level
    null/cardinality counts. No novel statistical method is used.
    References: pandas v2.x docs.

    EVIDENCE-SAFE: reports aggregate counts only. Raw row/cell values are
    never included in the output.
    """
    try:
        import pandas as pd
    except ImportError as _err:
        raise RuntimeError(
            "pandas is required for data-level diff. "
            "Install with: pip install pandas"
        ) from _err

    # Determine which tables appear in both sets.
    tables_a = set(output_fps_a)
    tables_b = set(output_fps_b)
    all_tables = sorted(tables_a | tables_b)

    table_deltas: list[dict[str, Any]] = []
    missing_files: list[str] = []
    any_data_change = False

    for table in all_tables:
        fp_a = output_fps_a.get(table) or {}
        fp_b = output_fps_b.get(table) or {}
        path_a_str = fp_a.get("path") if isinstance(fp_a, dict) else None
        path_b_str = fp_b.get("path") if isinstance(fp_b, dict) else None

        if not path_a_str or not path_b_str:
            # Table only in one run -- treat as a change
            any_data_change = True
            table_deltas.append(
                {
                    "table": table,
                    "row_count_a": None,
                    "row_count_b": None,
                    "row_count_delta": None,
                    "columns_added": [],
                    "columns_removed": [],
                    "column_deltas": [],
                    "note": "table only exists in one run",
                }
            )
            continue

        from pathlib import Path as _Path

        path_a = _Path(path_a_str)
        path_b = _Path(path_b_str)

        if not path_a.exists():
            missing_files.append(path_a_str)
        if not path_b.exists():
            missing_files.append(path_b_str)

        if missing_files:
            # Report missing but don't continue loading
            continue

        # Load data (CSV or Parquet by extension)
        def _load(p: "_Path") -> "pd.DataFrame":
            suffix = p.suffix.lower()
            if suffix == ".parquet":
                try:
                    return pd.read_parquet(str(p))
                except ImportError as _ie:
                    raise RuntimeError(
                        f"A Parquet reader (pyarrow or fastparquet) is required "
                        f"to read '{p.name}'. "
                        "Install with: pip install pyarrow"
                    ) from _ie
            return pd.read_csv(str(p), dtype=str)

        df_a = _load(path_a)
        df_b = _load(path_b)

        rows_a = len(df_a)
        rows_b = len(df_b)
        row_delta = rows_b - rows_a

        cols_a = set(df_a.columns)
        cols_b = set(df_b.columns)
        columns_added = sorted(cols_b - cols_a)
        columns_removed = sorted(cols_a - cols_b)
        common_cols = sorted(cols_a & cols_b)

        profile_a = _column_profile(df_a)
        profile_b = _column_profile(df_b)

        column_deltas: list[dict[str, Any]] = []
        for col in common_cols:
            pa = profile_a.get(col, {})
            pb = profile_b.get(col, {})
            nc_a = pa.get("null_count")
            nc_b = pb.get("null_count")
            uc_a = pa.get("unique_count")
            uc_b = pb.get("unique_count")
            dk_a = pa.get("dtype_kind")
            dk_b = pb.get("dtype_kind")
            dtype_changed = dk_a != dk_b

            nc_delta = (nc_b - nc_a) if (nc_a is not None and nc_b is not None) else None
            uc_delta = (uc_b - uc_a) if (uc_a is not None and uc_b is not None) else None

            has_col_change = bool(
                dtype_changed
                or (nc_delta is not None and nc_delta != 0)
                or (uc_delta is not None and uc_delta != 0)
            )
            if has_col_change:
                column_deltas.append(
                    {
                        "column": col,
                        "dtype_kind_a": dk_a,
                        "dtype_kind_b": dk_b,
                        "dtype_changed": dtype_changed,
                        "null_count_delta": nc_delta,
                        "unique_count_delta": uc_delta,
                    }
                )

        table_changed = bool(
            row_delta != 0 or columns_added or columns_removed or column_deltas
        )
        if table_changed:
            any_data_change = True

        table_deltas.append(
            {
                "table": table,
                "row_count_a": rows_a,
                "row_count_b": rows_b,
                "row_count_delta": row_delta,
                "columns_added": columns_added,
                "columns_removed": columns_removed,
                "column_deltas": column_deltas,
            }
        )

    return {
        "any_data_change": any_data_change,
        "table_deltas": table_deltas,
        "missing_files": missing_files,
    }


# ---------------------------------------------------------------------------
# CLI: report show <run-id>
# ---------------------------------------------------------------------------

_SHOW_EPILOG = """\
Examples:

  decoy report show <run-id>
    Resolve the run from the catalog and print a summary of its evidence.

  decoy report show <run-id> --format html --out report.html
    Write a full HTML report for the run's evidence.

  decoy report show <run-id> --json
    Emit the raw evidence manifest as structured JSON.

Resolution path:
  catalog run entry id -> metadata.evidence_path -> load manifest -> render.

Requirements:
  - A .decoy/ workspace must exist (run `decoy project init`).
  - The run entry must have an evidence_path (run with `--evidence-out`).

LOCAL ONLY: reads from the local DuckDB catalog and local evidence files.

See also: decoy jobs list, decoy report summarize, decoy report render.
"""


def _show(
    run_id: str = typer.Argument(
        ...,
        help="Run catalog id (or prefix, min 4 chars) from `decoy jobs list`.",
    ),
    format_: str = typer.Option(
        None,
        "--format",
        help=(
            "Output format when --out is given: 'html' or 'markdown'. "
            "Without --out, prints a terminal summary."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write the report to this file path (requires --format).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit the evidence manifest as JSON."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.",
    ),
) -> None:
    """Render the evidence report for a cataloged local run.

    Resolves the run from the catalog, loads its evidence manifest, and
    renders it using the same format as `decoy report summarize` (terminal)
    or `decoy report render` (file output with --format and --out).

    Requires the run to have been started with `decoy run --evidence-out`.
    LOCAL ONLY: does not connect to the platform server.
    """
    from decoy.cli.catalog import _catalog_db, _require_workspace
    from decoy.cli.jobs import _entry_to_run_dict, _lookup_run
    from decoy.ui.theme import code, error, success, warn

    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "report show", state)

    with _catalog_db(root, "report show", state) as conn:
        entry = _lookup_run(run_id, conn, "report show", state)

    run = _entry_to_run_dict(entry)
    evidence_path_str = run.get("evidence_path")

    if not evidence_path_str:
        msg = (
            f"Run {run_id!r} has no evidence path. "
            "Re-run with `decoy run pipeline.yaml --evidence-out evidence.json` "
            "to capture evidence, then register the run."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    evidence_file = Path(evidence_path_str)
    manifest = _load_manifest(evidence_file, state, "report show")

    # --json: emit the full manifest
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "report show",
                "status": "ok",
                "run_id": run["id"],
                "evidence_path": evidence_path_str,
                "manifest": manifest,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    # --format + --out: write file report
    if out is not None:
        fmt = (format_ or "html").lower().strip()
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
        fmt_label = "Markdown" if fmt in ("markdown", "md") else "HTML"
        state.console.print(success("ok"), f"{fmt_label} report written to", code(str(out)))
        return

    # Default: terminal summary (like report summarize)
    from decoy.ui.card import render_card
    from decoy.ui.table import make_table

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
    manifest_run_id = manifest.get("run_id", "?")

    fp_display = (pipeline_fp[:23] + "...") if len(pipeline_fp) > 23 else pipeline_fp

    facts: list[tuple[str, str]] = [
        ("Catalog run id", (run["id"][:16] + "...") if len(run["id"]) > 16 else run["id"]),
        ("Schema version", schema_v),
        ("Producer", producer),
        ("Run ID", (manifest_run_id[:16] + "...") if len(manifest_run_id) > 16 else manifest_run_id),
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
        command="decoy report show",
        facts=facts,
        next_hint=f"decoy report show {run_id} --format html --out report.html",
        status="warn" if warnings_list else "ok",
    )

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
# CLI: report diff <run-id-a> <run-id-b>
# ---------------------------------------------------------------------------

_DIFF_EPILOG = """\
Examples:

  decoy report diff <run-id-a> <run-id-b>
    Compare the output data files of two local runs at the data level.

  decoy report diff <run-id-a> <run-id-b> --json
    Emit structured JSON with per-table row-count and column-level deltas.

What diff compares:
  - Row counts per table (from actual data files)
  - Schema: columns added/removed/type-changed between runs
  - Per column: null-count delta, unique-count delta

What diff does NOT compare:
  - Raw row or cell values (never -- evidence-safe by design)
  - Platform-managed state, audit logs, or remote job history
  - Pipeline config changes (use `decoy report compare` for manifest-level diff)

Scope and limitations:
  - Requires both runs to have evidence files (`decoy run --evidence-out`).
  - Requires the output files referenced in the evidence manifests to still
    exist at their recorded paths.
  - Compares aggregate counts only -- not a full row-by-row diff.

Methodology: pandas.Series.nunique() / .isnull().sum() for column-level
counts (pandas v2.x). No novel statistical method is used.

See also: decoy report compare (manifest-level), decoy jobs list.
"""


def _diff(
    run_id_a: str = typer.Argument(
        ...,
        help="Catalog run id (or prefix) for the first run.",
    ),
    run_id_b: str = typer.Argument(
        ...,
        help="Catalog run id (or prefix) for the second run.",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit structured JSON."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.",
    ),
) -> None:
    """Compare output data files from two local runs at the data level.

    Resolves both run ids from the catalog, loads their evidence manifests,
    reads the output data files referenced in the manifests, and compares:
      - Per-table row counts
      - Schema (columns added/removed/type-changed)
      - Per-column null-count and unique-count deltas

    EVIDENCE-SAFE: only aggregate counts are reported -- no raw values.
    See `decoy report compare` for manifest-level (fingerprint) comparison.
    LOCAL ONLY: does not connect to the platform server.
    """
    from decoy.cli.catalog import _catalog_db, _require_workspace
    from decoy.cli.jobs import _entry_to_run_dict, _lookup_run
    from decoy.ui.table import make_table
    from decoy.ui.theme import code, error, hint, success, warn

    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "report diff", state)

    with _catalog_db(root, "report diff", state) as conn:
        entry_a = _lookup_run(run_id_a, conn, "report diff", state)
        entry_b = _lookup_run(run_id_b, conn, "report diff", state)

    run_a = _entry_to_run_dict(entry_a)
    run_b = _entry_to_run_dict(entry_b)

    # Require evidence paths for both runs
    def _get_evidence(run: dict[str, Any], label: str) -> dict[str, Any]:
        ev_path = run.get("evidence_path")
        if not ev_path:
            msg = (
                f"Run {label!r} has no evidence path. "
                "Re-run with `decoy run --evidence-out evidence.json` to capture evidence."
            )
            if state.mode is OutputMode.json:
                emit_json(state, {"command": "report diff", "status": "error", "error": msg})
            elif state.mode is not OutputMode.quiet:
                state.err_console.print(error("error:"), msg)
            raise typer.Exit(code=EXIT_USAGE)
        manifest = _load_manifest(Path(ev_path), state, "report diff")
        return manifest

    manifest_a = _get_evidence(run_a, run_id_a)
    manifest_b = _get_evidence(run_b, run_id_b)

    out_fps_a: dict[str, Any] = manifest_a.get("output_fingerprints") or {}
    out_fps_b: dict[str, Any] = manifest_b.get("output_fingerprints") or {}

    # Perform data-level comparison
    try:
        diff_result = compare_data(out_fps_a, out_fps_b)
    except RuntimeError as _dep_err:
        _msg = str(_dep_err)
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report diff", "status": "error", "error": _msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), _msg)
        raise typer.Exit(code=EXIT_RUNTIME)

    # Handle missing files
    if diff_result["missing_files"]:
        msg = (
            "Output files are missing and cannot be compared: "
            + ", ".join(diff_result["missing_files"])
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report diff", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("note:"),
                "Output files may have been moved or deleted after the run completed.",
            )
        raise typer.Exit(code=EXIT_USAGE)

    if state.mode is OutputMode.json:
        payload: dict[str, Any] = {
            "command": "report diff",
            "status": "ok",
            "run_id_a": run_a["id"],
            "run_id_b": run_b["id"],
            "any_data_change": diff_result["any_data_change"],
            "table_deltas": diff_result["table_deltas"],
            "scope": (
                "data-level aggregate counts only; raw values not included. "
                "LOCAL ONLY -- does not reflect platform state."
            ),
        }
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    any_change = diff_result["any_data_change"]
    if not any_change:
        state.console.print(
            success("ok"),
            "no data changes detected between the two runs.",
        )
        state.console.print(
            " ",
            hint("note:"),
            "row counts, schema, and column-level stats are identical.",
        )
        state.console.print(
            " ",
            hint("scope:"),
            "aggregate counts only; raw values not included.",
        )
        return

    state.console.print(
        warn("data changes detected"),
        "between",
        code(run_id_a[:8] + "..."),
        "and",
        code(run_id_b[:8] + "..."),
    )
    state.console.print("")

    for td in diff_result["table_deltas"]:
        tname = td["table"]
        row_delta = td.get("row_count_delta")
        added = td.get("columns_added") or []
        removed = td.get("columns_removed") or []
        col_deltas = td.get("column_deltas") or []

        if (
            (row_delta is not None and row_delta != 0)
            or added
            or removed
            or col_deltas
        ):
            state.console.print(warn(f"table: {tname}"))
            if row_delta is not None and row_delta != 0:
                sign = "+" if row_delta > 0 else ""
                state.console.print(
                    " ",
                    hint("row count:"),
                    code(str(td.get("row_count_a"))),
                    "->",
                    code(str(td.get("row_count_b"))),
                    hint(f"({sign}{row_delta})"),
                )
            if added:
                state.console.print(
                    " ", hint("columns added:"), code(", ".join(added))
                )
            if removed:
                state.console.print(
                    " ", hint("columns removed:"), code(", ".join(removed))
                )
            if col_deltas:
                t = make_table(
                    "Column", "Null Count Delta", "Unique Count Delta", "Dtype Changed",
                    title=f"{tname} column deltas"
                )
                for cd in col_deltas:
                    nc_d = str(cd.get("null_count_delta", ""))
                    uc_d = str(cd.get("unique_count_delta", ""))
                    dtype_ch = "yes" if cd.get("dtype_changed") else "no"
                    t.add_row(cd["column"], nc_d, uc_d, dtype_ch)
                state.console.print(t)

    state.console.print("")
    state.console.print(
        " ",
        hint("scope:"),
        "aggregate counts only; raw values not included. "
        "Use `decoy report compare` for manifest-level fingerprint comparison.",
    )


# ---------------------------------------------------------------------------
# Command registration (continued)
# ---------------------------------------------------------------------------

report_app.command(name="render", epilog=_RENDER_EPILOG)(_render)
report_app.command(name="summarize", epilog=_SUMMARIZE_EPILOG)(_summarize)
report_app.command(name="compare", epilog=_COMPARE_EPILOG)(_compare)
report_app.command(name="show", epilog=_SHOW_EPILOG)(_show)
report_app.command(name="diff", epilog=_DIFF_EPILOG)(_diff)

# Public exports
__all__ = [
    "compare_data",
    "compare_manifests",
    "render_html",
    "render_markdown",
    "report_app",
]
