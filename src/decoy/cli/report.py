"""``decoy report`` -- the single post-run surface over local run artifacts.

Every subcommand is file-first: it reads only the evidence manifest path(s) it
is given (and, where noted, the source/output data files those manifests or
arguments reference). There is no run catalog or workspace.

  show      -- Summarize one evidence manifest (the union card) or render a file.
  render    -- Write an HTML or Markdown report to a file.
  verify    -- Re-hash the recorded files and report fingerprint drift.
  fidelity  -- Recompute distribution fidelity between a source and an output.
  integrity -- Verify a masked file against its pre-mask source (post-mask checks).
  diff      -- Compare two manifests: fingerprints always, data when files exist.
  vault     -- Inspect a vault file written by `decoy run --vault`.

S4b (CLI redesign) folded the former `report summarize` + `report compare`,
the `evidence` verbs (show/verify), the `validate` distribution check, the
`storm` integrity check, and `vault info` into this one noun. The relocated
bodies are reused verbatim; their engine deps stay lazy-imported inside each
body.

RAW-VALUE ISOLATION (Dennis review note, cli-first-capability-guide.md L534-538):

  Reports build from evidence-safe data only. The manifest already excludes
  raw row values (strategy names + fingerprints + metadata only), so rendering
  the manifest is safe by construction.

  The manifest renderers accept a manifest DICT and render it. They do NOT:
    - Read source or output CSV files from disk.
    - Embed raw cell/row values in any report.
    - Render full STORM profiles or raw diagnostic values.

  What is intentionally excluded is stated in each report footer so reviewers
  know the omission is deliberate. (`fidelity`/`integrity` DO read the data
  files they are pointed at, by design -- they report aggregate metrics only.)
"""

from __future__ import annotations

import html as _html_mod
import json as _json
from pathlib import Path
from typing import Any

import typer

from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.evidence import _render_manifest_card, verify_manifest
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, info, risk_high, success, warn

# Grade -> minimum overall_score, mirroring the engine's own grade thresholds
# (decoy_engine.quality.report._GRADE_THRESHOLDS: A >= 0.95, B >= 0.85,
# C >= 0.70, D >= 0.50). Moved verbatim with the `fidelity` body from
# validate.py (S4b): the engine maps score -> grade but exposes no reverse
# (grade -> score) helper, so `--min-grade` needs its own copy of the table.
_GRADE_MIN_SCORE: dict[str, float] = {"A": 0.95, "B": 0.85, "C": 0.70, "D": 0.50}

# ---------------------------------------------------------------------------
# Typer app registration
# ---------------------------------------------------------------------------

report_app = typer.Typer(
    name="report",
    help=(
        "The post-run surface: show / render / verify / fidelity / integrity / "
        "diff / vault. Operates on files -- evidence manifests produced by "
        "`decoy run --evidence-out` plus the source/output data they reference."
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

  decoy report render evidence.json --output report.html
    Render the manifest as a self-contained offline HTML report.

  decoy report render evidence.json --format markdown --output report.md
    Render the manifest as a plain Markdown report.

What the report includes:
  Run summary, pipeline identity (fingerprint), input/output fingerprints,
  row counts, masking strategies (names only), node timings, and warnings.

What the report intentionally excludes:
  Raw row values, PII samples, STORM profile internals, diagnostic values.
  The evidence manifest records strategy names and fingerprints only; the
  report renders that safe subset.

See also: decoy report show, decoy report diff, decoy report verify.
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
        "--output",
        "-o",
        help="Output file path (e.g. report.html or report.md).",
    ),
    format_: str = typer.Option(
        "html",
        "--format",
        help="Output format: 'html' (default) or 'markdown'.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON record of what was written instead of the human summary.",
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
    state = setup_output(json_, quiet, verbose)
    manifest = _load_manifest(evidence_file, state, "report render")

    fmt = format_.lower().strip()
    if fmt not in ("html", "markdown", "md"):
        msg = f"unknown format {format_!r}; use 'html' or 'markdown'."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report render", "status": "error", "error": msg})
        else:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    if fmt in ("markdown", "md"):
        content = render_markdown(manifest)
    else:
        content = render_html(manifest)

    try:
        out.write_text(content, encoding="utf-8")
    except OSError as exc:
        msg = f"could not write {out}: {exc}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report render", "status": "error", "error": msg})
        else:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    fmt_label = "Markdown" if fmt in ("markdown", "md") else "HTML"

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "report render",
                "status": "ok",
                "evidence_file": str(evidence_file),
                "output": str(out),
                "format": fmt_label.lower(),
            },
        )
        return

    if state.mode is not OutputMode.quiet:
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
# Manifest-level compare rendering (shared by `report diff`)
# ---------------------------------------------------------------------------


def _render_manifest_compare(state: Any, diff: dict[str, Any]) -> None:
    """Render a `compare_manifests` result to the terminal (shared helper).

    Prints the pipeline-fingerprint change, per-table input/output fingerprint
    changes, row-count deltas, and warnings added/removed. Caller decides the
    headline and whether any change was found.
    """
    from decoy.ui.table import make_table

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
        if not path_b.exists() and path_b_str not in missing_files:
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

        try:
            df_a = _load(path_a)
            df_b = _load(path_b)
        except (OSError, ValueError):
            # The file exists but could not be read (corrupt, truncated, or not
            # the format its extension claims; a parquet reader raises
            # ArrowInvalid/ValueError, a bad path raises OSError). Degrade this
            # table to the same data-unavailable handling as a missing file so
            # one broken output cannot crash the whole comparison -- the caller
            # still reports manifest level and --require-data still hard-fails.
            # The raw parser message is deliberately dropped: it can echo file
            # bytes or cell values (observability leak rule). A missing parquet
            # reader surfaces as RuntimeError, which is not caught here and
            # propagates to the caller's dependency boundary.
            for p_str in (path_a_str, path_b_str):
                if p_str not in missing_files:
                    missing_files.append(p_str)
            continue

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
# CLI: report show MANIFEST
# ---------------------------------------------------------------------------

_SHOW_EPILOG = """\
Examples:

  decoy report show evidence.json
    Print a summary of the evidence manifest to the terminal.

  decoy report show evidence.json --format html --output report.html
    Write a full HTML report from the evidence manifest.

  decoy report show evidence.json --json
    Emit the raw evidence manifest as structured JSON.

The terminal card is the UNION of the former `report summarize` + `evidence
show`: run metadata + manifest_hash integrity status, input/output fingerprint
tables, masking strategies, and row counts.

Requirements:
  - An evidence manifest JSON produced by `decoy run --evidence-out`.

See also: decoy report render, decoy report verify.
"""


def _show(
    evidence_file: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to an evidence manifest JSON (from `decoy run --evidence-out`).",
    ),
    format_: str = typer.Option(
        None,
        "--format",
        help=(
            "Output format when --output is given: 'html' or 'markdown'. "
            "Without --output, prints a terminal summary."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the report to this file path (requires --format).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit the evidence manifest as JSON."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
) -> None:
    """Render the evidence report from an evidence manifest file.

    Loads the evidence manifest at the given path and renders the UNION card
    (the former `report summarize` + `evidence show`): run metadata +
    manifest_hash integrity status, input/output fingerprint tables, masking
    strategies, and row counts. With --format + --output it instead writes an
    HTML or Markdown report (like `decoy report render`).

    Reads only the file it is given; never connects to a server or catalog.
    """
    state = setup_output(json_, quiet, verbose)
    manifest = _load_manifest(evidence_file, state, "report show")

    # --json: emit the full manifest
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "report show",
                "status": "ok",
                "evidence_file": str(evidence_file),
                "manifest": manifest,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    # --format + --output: write file report
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

    # Default: the union card -- fingerprint tables + strategies + manifest_hash
    # status (from the former `evidence show`) PLUS the row_counts table (from
    # the former `report summarize`/`show`).
    from decoy.ui.table import make_table

    _render_manifest_card(state, manifest, evidence_file)

    row_counts: dict[str, Any] = manifest.get("row_counts") or {}
    if row_counts:
        t = make_table("Table", "Rows", title="Row counts")
        for tname, count in row_counts.items():
            t.add_row(str(tname), str(count))
        state.console.print(t)


# ---------------------------------------------------------------------------
# CLI: report diff MANIFEST_A MANIFEST_B
# ---------------------------------------------------------------------------

_DIFF_EPILOG = """\
Examples:

  decoy report diff a.json b.json
    Compare two evidence manifests. Always runs the manifest/fingerprint-level
    comparison (pipeline + per-table fingerprints + row-count deltas +
    warnings). If the referenced output files still exist, ALSO runs the
    data-level comparison (row/column counts read from the CSV/Parquet).

  decoy report diff a.json b.json --json
    Emit structured JSON: manifest-level fields always, plus any_data_change +
    table_deltas when the output files were present.

  decoy report diff a.json b.json --require-data
    Hard-fail (exit 1) if any referenced output file is missing, instead of
    degrading to manifest-level only. For scripted callers that need the
    data-level comparison to have run.

What diff compares at the MANIFEST level (always):
  - Pipeline fingerprint change.
  - Per-table input/output fingerprint changes (added/removed/changed).
  - Row count deltas per table.
  - Warnings added or removed.

What diff compares at the DATA level (when output files exist):
  - Row counts per table (from the actual data files).
  - Schema: columns added/removed/type-changed.
  - Per column: null-count delta, unique-count delta.

What diff does NOT compare:
  - Raw row or cell values (never -- evidence-safe by design).
  - Platform-managed state, audit logs, or remote job history.

Missing output files are a NOTE, not a failure: the manifest-level comparison
still runs. Pass --require-data to restore the strict hard-fail.

Methodology: pandas.Series.nunique() / .isnull().sum() for column-level
counts (pandas v2.x). No novel statistical method is used.
"""


def _diff(
    evidence_file_a: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to the first evidence manifest JSON.",
    ),
    evidence_file_b: Path = typer.Argument(
        ...,
        exists=False,
        dir_okay=False,
        help="Path to the second evidence manifest JSON.",
    ),
    require_data: bool = typer.Option(
        False,
        "--require-data",
        help=(
            "Hard-fail (EXIT_USAGE) when a referenced output file is missing, "
            "instead of degrading to manifest-level only."
        ),
    ),
    json_: bool = typer.Option(False, "--json", help="Emit structured JSON."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
) -> None:
    """Compare two evidence manifests: fingerprints always, data when present.

    A lossless superset of the former `report diff` (data-level) and `report
    compare` (manifest-level). It ALWAYS runs the manifest/fingerprint-level
    comparison (works even when output files are gone). It ADDITIONALLY runs
    the data-level comparison (reading the CSV/Parquet the manifests
    reference) when those output files exist; when a file is missing it prints
    a note and reports manifest-level only -- unless --require-data is set,
    which restores the strict hard-fail.

    EVIDENCE-SAFE: only aggregate counts are reported -- no raw values.
    Reads only the files it is given; never connects to a server or catalog.
    """
    state = setup_output(json_, quiet, verbose)

    manifest_a = _load_manifest(evidence_file_a, state, "report diff")
    manifest_b = _load_manifest(evidence_file_b, state, "report diff")

    # --- Manifest/fingerprint-level comparison (always) ---
    manifest_diff = compare_manifests(manifest_a, manifest_b)

    out_fps_a: dict[str, Any] = manifest_a.get("output_fingerprints") or {}
    out_fps_b: dict[str, Any] = manifest_b.get("output_fingerprints") or {}

    # --- Data-level comparison (when the referenced output files exist) ---
    data_result: dict[str, Any] | None = None
    data_dep_error: str | None = None
    try:
        data_result = compare_data(out_fps_a, out_fps_b)
    except RuntimeError as _dep_err:
        # pandas (or a parquet reader) is not installed. Treat the data level
        # as unavailable rather than failing the whole comparison.
        data_dep_error = str(_dep_err)

    missing_files: list[str] = (
        list(data_result["missing_files"]) if data_result else []
    )
    data_available = data_result is not None and not missing_files

    # --require-data: restore the strict hard-fail when the data level could
    # not run (missing output files, or no pandas).
    if require_data and not data_available:
        if missing_files:
            msg = (
                "Output files are missing or unreadable and cannot be compared: "
                + ", ".join(missing_files)
            )
        else:
            msg = data_dep_error or "data-level comparison is unavailable."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "report diff", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("note:"),
                "output files may have been moved, deleted, or corrupted after "
                "the run completed; drop --require-data for manifest-level only.",
            )
        raise typer.Exit(code=EXIT_USAGE)

    # --- JSON envelope: manifest-level fields always, data-level when ran ---
    if state.mode is OutputMode.json:
        payload: dict[str, Any] = {
            "command": "report diff",
            "status": "ok",
            "evidence_file_a": str(evidence_file_a),
            "evidence_file_b": str(evidence_file_b),
        }
        payload.update(manifest_diff)
        if data_available and data_result is not None:
            payload["data_level"] = "compared"
            payload["any_data_change"] = data_result["any_data_change"]
            payload["table_deltas"] = data_result["table_deltas"]
        else:
            payload["data_level"] = "skipped"
            payload["any_data_change"] = None
            payload["table_deltas"] = []
            payload["missing_files"] = missing_files
            if data_dep_error:
                payload["data_note"] = data_dep_error
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # --- Human-readable: manifest level first, then data level ---
    manifest_changed = manifest_diff["any_change"]
    data_changed = bool(data_available and data_result and data_result["any_data_change"])

    if not manifest_changed and not data_changed:
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
    else:
        state.console.print(
            warn("changes detected"),
            "between",
            code(str(evidence_file_a)),
            "and",
            code(str(evidence_file_b)),
        )
        state.console.print("")
        if manifest_changed:
            state.console.print(accent("Manifest level:"))
            _render_manifest_compare(state, manifest_diff)

    # Data-level section (only when it ran).
    if data_available and data_result is not None:
        state.console.print("")
        state.console.print(accent("Data level:"))
        if not data_result["any_data_change"]:
            state.console.print(
                success("ok"),
                "row counts, schema, and column-level stats are identical.",
            )
        else:
            _render_data_diff(state, data_result)
        state.console.print(
            " ",
            hint("scope:"),
            "aggregate counts only; raw values not included.",
        )
    else:
        # Degraded: the output files are gone. Note, not failure.
        state.console.print("")
        note = (
            "output files missing (" + ", ".join(missing_files) + ")"
            if missing_files
            else (data_dep_error or "data-level comparison unavailable")
        )
        state.err_console.print(
            " ",
            hint("note:"),
            f"data-level comparison skipped: {note}; reported manifest-level "
            "only. Pass --require-data to hard-fail instead.",
        )


def _render_data_diff(state: Any, diff_result: dict[str, Any]) -> None:
    """Render a `compare_data` result to the terminal (per-table deltas)."""
    from decoy.ui.table import make_table

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


# ---------------------------------------------------------------------------
# CLI: report verify MANIFEST  (relocated from `evidence verify`, S4b)
# ---------------------------------------------------------------------------

_VERIFY_EPILOG = """\
Examples:

  decoy report verify evidence.json
    Check all fingerprints (pipeline, inputs, outputs, manifest integrity).
    Exits 0 when all match; non-zero when any changed.

  decoy report verify evidence.json --json
    Emit a structured JSON result with the list of issues found.

What verify checks:
  - manifest_hash: detects edits to the manifest JSON file.
  - pipeline_fingerprint: detects changes to pipeline.yaml.
  - input_fingerprints: detects changes to source data files.
  - output_fingerprints: detects changes to masked/generated output files.

What verify does NOT check:
  - Whether the output was produced by the declared pipeline.
  - Data correctness or masking quality.
  - Platform audit logs, RBAC, or schedule history.
  - Network, vault, or secrets accessibility.

Integrity limit: manifest_hash is an UNKEYED SHA-256 check. It detects
accidental drift; it does NOT detect a motivated tamperer who can edit the
manifest and recompute the hash. Keyed signing is platform R4 territory.

Exit codes: 0 clean; 4 fingerprint drift detected; 1 bad input.

See also: decoy report show, decoy run --evidence-out.
"""


def _verify(
    evidence_file: Path = typer.Argument(
        ...,
        exists=False,  # checked via _load_manifest for a cleaner error
        dir_okay=False,
        help="Path to a local evidence manifest JSON.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result instead of human-readable output.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Exit code carries the result."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Verify a local evidence manifest's fingerprints against current files.

    Re-hashes the pipeline config, input files, and output files and
    compares against the fingerprints recorded in the manifest. Also checks
    manifest_hash to detect edits to the manifest file itself.

    Exits 0 when all fingerprints match (no drift). Exits non-zero
    (EXIT_FINDINGS) when any fingerprint has changed.

    Distinct from `report integrity` (post-mask residual-PII / FK / policy on
    a masked file plus `--source`): verify is manifest fingerprint-drift.

    Integrity limit: manifest_hash is an UNKEYED SHA-256 check. It detects
    accidental drift (file changes since the run), NOT a motivated tamperer
    who can edit the manifest and recompute the hash. Keyed signing (R4) is
    required for adversarial authenticity guarantees.
    """
    state = setup_output(json_, quiet, verbose)
    manifest = _load_manifest(evidence_file, state, "report verify")

    issues = verify_manifest(manifest)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "report verify",
                "status": "ok" if not issues else "fingerprint_mismatch",
                "evidence_file": str(evidence_file),
                "issues": issues,
                "issue_count": len(issues),
            },
        )
        if issues:
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    if state.mode is OutputMode.quiet:
        if issues:
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    if not issues:
        state.console.print(
            success("OK"),
            f"All fingerprints match. ({evidence_file.name})",
        )
        return

    state.err_console.print(
        error("INTEGRITY CHECK FAILED: fingerprint mismatch"),
        f"{len(issues)} fingerprint(s) changed in {evidence_file.name}",
    )
    for issue in issues:
        state.err_console.print(" ", hint("-"), issue)
    state.err_console.print(
        " ",
        hint("hint:"),
        "files may have changed since the evidence was recorded, "
        "or the manifest file may have been edited.",
    )
    state.err_console.print(
        " ",
        hint("note:"),
        "manifest_hash is an UNKEYED SHA-256 check; it detects accidental "
        "drift, not adversarial edits. Keyed signing is platform R4 territory.",
    )
    raise typer.Exit(code=EXIT_FINDINGS)


# ---------------------------------------------------------------------------
# CLI: report fidelity SOURCE OUTPUT  (relocated from the `validate` group)
# ---------------------------------------------------------------------------

_FIDELITY_EPILOG = """\
Examples:

  decoy report fidelity source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output. Report mode (record only): always exits 0.

  decoy report fidelity source.csv output.csv --config pipeline.yaml
    Pass the pipeline config so intentional loss (hash, bucketize, ...)
    is not flagged as accidental drift.

  decoy report fidelity source.csv synthetic.csv --generate
    Row counts are expected to differ (synthetic generation, not masking).

  decoy report fidelity source.csv output.csv --mode fail --min-grade B
    Exit non-zero (EXIT_FINDINGS) when the overall grade falls below B.

  decoy report fidelity source.csv output.csv --joint state,tier --json
    Include a (state, tier) joint fidelity score; emit the full
    quality-report/v1 + policy JSON.

  decoy report fidelity source.csv output.csv --report-out report.json
    Also write the full report + policy verdict to disk.

Exit codes: 0 pass (or warn without --fail-on-warning); 4 EXIT_FINDINGS
when the policy verdict is fail, or warn with --fail-on-warning set;
1 EXIT_USAGE for bad input (missing columns, unreadable CSV, bad flags).

See also: decoy report integrity, decoy fit, decoy run.
"""


def _build_strategy_map(config_dict: dict[str, Any]) -> dict[str, str]:
    """Flatten column -> strategy across every declared table.

    Mirrors the evidence manifest's strategy-summary loop
    (`decoy.cli.evidence.build_manifest`). `report fidelity` checks a single
    source/output CSV pair, not a specific table, so this assumes column names
    are unique across the pipeline's declared tables; a multi-table config
    with a repeated column name lets the last table's strategy win. Acceptable
    for the v1 single source/output scope (D4).
    """
    strategy_map: dict[str, str] = {}
    for table in config_dict.get("tables") or []:
        if not isinstance(table, dict):
            continue
        for col in table.get("columns") or []:
            if isinstance(col, dict) and col.get("name"):
                strategy_map[col["name"]] = col.get("strategy", "")
        for gen_col in table.get("generate_columns") or []:
            if isinstance(gen_col, dict) and gen_col.get("name"):
                strategy_map[gen_col["name"]] = "generate"
    return strategy_map


def _fidelity(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Pre-mask / pre-generate source CSV (ground truth).",
    ),
    output: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Post-mask / post-generate output CSV to check.",
    ),
    joint: list[str] = typer.Option(
        [],
        "--joint",
        help="Column pair 'a,b' to also score jointly (repeatable).",
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        help=(
            "Output is synthetic generation, not masking: row counts may "
            "legitimately differ (sets expect_row_parity=False). Default "
            "assumes masking (row parity expected)."
        ),
    ),
    pipeline_config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Pipeline YAML naming each column's strategy, so intentional "
            "loss (hash, bucketize, faker, ...) is not flagged as accidental "
            "drift. Without it, per-column policy checks run on defaults only."
        ),
    ),
    policy: Path | None = typer.Option(
        None,
        "--policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "A quality-policy config (YAML or JSON: mode / thresholds / "
            "strategy_expectations) overriding --mode / --min-grade / --min-score."
        ),
    ),
    mode: str = typer.Option(
        "report",
        "--mode",
        help=(
            "report (record only, verdict always pass) | warn (violations "
            "promote verdict to warn) | fail (violations promote verdict to "
            "fail). Ignored when --policy sets its own mode."
        ),
    ),
    min_grade: str | None = typer.Option(
        None,
        "--min-grade",
        help="Shorthand: minimum letter grade (A/B/C/D) the overall score must reach.",
    ),
    min_score: float | None = typer.Option(
        None,
        "--min-score",
        help="Shorthand: minimum overall_score in [0, 1].",
    ),
    fail_on_warning: bool = typer.Option(
        False,
        "--fail-on-warning",
        help="Also exit non-zero (EXIT_FINDINGS) when the policy verdict is 'warn'.",
    ),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Write the full quality-report/v1 + policy JSON to this path.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full quality-report/v1 + policy result as JSON.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Recompute distribution fidelity between a source and an output CSV.

    Wraps `decoy_engine.quality.compute_quality_report` +
    `apply_quality_policy` (report.py:97, policy.py:142): the engine owns
    every metric and the letter grade; this command computes no fidelity
    number itself. Reads both CSVs fresh on every invocation (pure,
    repeatable) -- the CLI's local evidence manifest records file
    fingerprints but not the raw frames, so recomputing from the two files
    is the only honest source for this number (BF1).

    Exit codes: 0 when the policy verdict is 'pass' (or 'warn' without
    --fail-on-warning); EXIT_FINDINGS (4) when the verdict is 'fail', or
    'warn' with --fail-on-warning set. This mirrors `report integrity`'s
    exit-code contract -- a data-audit verb that reports findings, not a run
    that crashed -- rather than EXIT_RUNTIME (reserved for the CLI/engine
    blowing up unexpectedly).
    """
    import yaml as _yaml

    state = setup_output(json_, quiet, verbose)
    source_str = str(source)
    output_str = str(output)

    def _emit_error(message: str) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "report fidelity",
                    "status": "error",
                    "source": source_str,
                    "output": output_str,
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            _emit_error(f"--joint expects 'colA,colB'; got {spec!r}.")
            raise typer.Exit(code=EXIT_USAGE)
        joint_pairs.append((parts[0], parts[1]))

    if min_grade is not None and min_score is not None:
        _emit_error("specify only one of --min-grade / --min-score, not both.")
        raise typer.Exit(code=EXIT_USAGE)

    if min_grade is not None and min_grade.upper() not in _GRADE_MIN_SCORE:
        _emit_error(f"--min-grade must be one of A, B, C, D; got {min_grade!r}.")
        raise typer.Exit(code=EXIT_USAGE)

    if mode not in ("report", "warn", "fail"):
        _emit_error(f"--mode must be one of report, warn, fail; got {mode!r}.")
        raise typer.Exit(code=EXIT_USAGE)

    strategy_map: dict[str, str] = {}
    if pipeline_config is not None:
        from decoy_engine import PipelineConfig

        try:
            raw_cfg = _yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
            config_dict = PipelineConfig.model_validate(raw_cfg).model_dump()
        except _yaml.YAMLError as exc:
            # YAMLError carries the offending source line verbatim; sanitize it.
            _emit_error(sanitize_yaml_error(exc))
            raise typer.Exit(code=EXIT_USAGE)
        except Exception as exc:
            _emit_error(f"could not parse --config {pipeline_config}: {exc}")
            raise typer.Exit(code=EXIT_USAGE)
        strategy_map = _build_strategy_map(config_dict)

    if policy is not None:
        try:
            policy_config = _yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        except _yaml.YAMLError as exc:
            _emit_error(sanitize_yaml_error(exc))
            raise typer.Exit(code=EXIT_USAGE)
        except Exception as exc:
            _emit_error(f"could not parse --policy {policy}: {exc}")
            raise typer.Exit(code=EXIT_USAGE)
        if not isinstance(policy_config, dict):
            _emit_error(f"--policy {policy} must be a YAML/JSON mapping.")
            raise typer.Exit(code=EXIT_USAGE)
    else:
        thresholds: dict[str, Any] = {}
        if min_score is not None:
            thresholds["overall"] = {"min": min_score}
        elif min_grade is not None:
            thresholds["overall"] = {"min": _GRADE_MIN_SCORE[min_grade.upper()]}
        policy_config = {"mode": mode, "thresholds": thresholds}

    import pandas as pd
    from decoy_engine.quality import apply_quality_policy, compute_quality_report

    try:
        src_df = pd.read_csv(source)
    except Exception as exc:
        _emit_error(f"could not read {source}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    try:
        out_df = pd.read_csv(output)
    except Exception as exc:
        _emit_error(f"could not read {output}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    report = compute_quality_report(
        src_df,
        out_df,
        joint_columns=joint_pairs or None,
        expect_row_parity=not generate,
    )
    policy_result = apply_quality_policy(report, policy_config, strategy_map=strategy_map)

    if report_out is not None:
        report_out.write_text(
            _json.dumps({**report, "policy": policy_result}, indent=2),
            encoding="utf-8",
        )

    verdict = policy_result["verdict"]
    status = "ok" if verdict == "pass" else verdict

    if state.mode is OutputMode.json:
        envelope = dict(report)
        envelope["command"] = "report fidelity"
        envelope["status"] = status
        envelope["policy"] = policy_result
        emit_json(state, envelope)
    elif state.mode is not OutputMode.quiet:
        _render_fidelity_report(state, report, policy_result)

    if verdict == "fail" or (verdict == "warn" and fail_on_warning):
        raise typer.Exit(code=EXIT_FINDINGS)


def _render_fidelity_report(
    state: Any,
    report: dict[str, Any],
    policy_result: dict[str, Any],
) -> None:
    """Human-readable rendering of a quality-report/v1 + policy result."""
    from decoy.ui.table import make_table

    grade = report.get("grade", "unavailable")
    overall = report.get("overall_score")
    overall_str = f"{overall:.3f}" if isinstance(overall, (int, float)) else "n/a"
    verdict = policy_result.get("verdict", "pass")

    if verdict == "pass":
        verdict_text = success(verdict.upper())
    elif verdict == "warn":
        verdict_text = warn(verdict.upper())
    else:
        verdict_text = error(verdict.upper())
    state.console.print(verdict_text, f"grade {grade}  overall_score {overall_str}")

    columns = report.get("marginal", {}).get("columns", [])
    if columns:
        table = make_table("Column", "Comparable", "Similarity", title="Marginal fidelity")
        for col in columns:
            if not isinstance(col, dict):
                continue
            sim = col.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            table.add_row(
                str(col.get("column", "?")),
                "yes" if col.get("comparable") else "no",
                sim_str,
            )
        state.console.print(table)

    joints = report.get("pairwise", {}).get("joints", [])
    if joints:
        table = make_table("Joint", "Comparable", "Similarity", title="Pairwise fidelity")
        for j in joints:
            if not isinstance(j, dict):
                continue
            sim = j.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            table.add_row(
                "x".join(j.get("columns", [])),
                "yes" if j.get("comparable") else "no",
                sim_str,
            )
        state.console.print(table)

    violations = policy_result.get("violations", [])
    if violations:
        table = make_table("Check", "Column", "Expected", "Actual", title="Policy violations")
        for v in violations:
            table.add_row(
                str(v.get("check", "?")),
                str(v.get("column", "-")),
                str(v.get("expected", "-")),
                str(v.get("actual", "-")),
            )
        state.console.print(table)
    elif verdict == "pass":
        state.console.print(success("OK"), "no policy violations.")


# ---------------------------------------------------------------------------
# CLI: report integrity MASKED --source SRC  (relocated from the `storm` group)
# ---------------------------------------------------------------------------

_INTEGRITY_EPILOG = """\
Examples:

  decoy report integrity masked.csv --source source.csv
    Run all three post-mask checks (residual_pii + fk_preservation +
    policy_validation) against a masked file with its pre-mask
    baseline as ground truth. Render a Rich findings table.

  decoy report integrity masked.csv --source source.csv --config pipeline.yaml
    Same, but load the pipeline YAML so policy_validation can
    compare against the configured masks. Without --config the
    runner still produces residual_pii findings; policy_validation
    is reduced to "no config provided" notes.

  decoy report integrity masked.csv --source source.csv --json > report.json
    Pipe the full JobStormReport-shaped JSON for downstream tooling.

  decoy report integrity masked.csv --source source.csv --output report.json
    Write JSON to file + render a Rich summary on stderr.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy report verify, decoy report fidelity, decoy explain exit-codes.
"""


def _integrity(
    masked: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the masked CSV to verify.",
    ),
    source: Path = typer.Option(
        ...,
        "--source",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Pre-mask source CSV (ground truth for the integrity check).",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Optional pipeline.yaml. When passed, policy_validation can "
            "compare against the configured masks. Without it the runner "
            "still produces residual_pii + fk_preservation findings."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Write the JobStormReport JSON to this path. The Rich table "
            "still renders to stderr."
        ),
    ),
    allow_source_mismatch: bool = typer.Option(
        False,
        "--allow-source-mismatch",
        help=(
            "Suppress the stderr warning when --source does not match "
            "the pipeline's declared sources block."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full JobStormReport JSON to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Verify a masked file's integrity against its pre-mask source.

    Wraps `decoy_engine.storm.postmask.run_storm_post_mask`. Runs the
    three post-mask check buckets (residual_pii, fk_preservation,
    policy_validation) the platform's mask job already runs when
    `run_storm: true` is declared in the pipeline; this verb lets the
    CLI user run the same checks standalone.

    Distinct from `report verify` (manifest fingerprint-drift): integrity is
    post-mask residual-PII / FK / policy on a masked file plus --source.

    Exit codes: 0 clean; 4 EXIT_FINDINGS on any fail-severity finding;
    1 EXIT_USAGE for missing files; 3 EXIT_RUNTIME for unexpected
    exceptions.
    """
    import pandas as pd

    from decoy.ui.table import make_table

    state = setup_output(json_, quiet, verbose)
    masked_str = str(masked)
    source_str = str(source)

    try:
        from decoy_engine.storm.postmask import run_storm_post_mask

        source_df = pd.read_csv(source)
        masked_df = pd.read_csv(masked)

        config_dict: dict
        table_name: str
        if config is not None:
            import yaml as _yaml
            from decoy_engine import PipelineConfig

            try:
                raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
            except _yaml.YAMLError as exc:
                # The outer handler renders str(exc); a raw YAMLError there would
                # echo the offending source line. Re-raise a pre-sanitized message.
                raise ValueError(sanitize_yaml_error(exc)) from None
            config_dict = PipelineConfig.model_validate(raw).model_dump()
            # Pick the first declared table name. Mixed-mode configs
            # can declare multiple; the CLI verb today handles a single
            # source/masked pair, so we anchor on the first table the
            # pipeline declared and warn if the user passed a source
            # that points elsewhere.
            tables = config_dict.get("tables") or []
            table_name = tables[0]["name"] if tables else masked.stem
            declared_sources = config_dict.get("sources") or {}
            declared_path = None
            if table_name in declared_sources:
                declared_path = declared_sources[table_name].get("path")
            if (
                declared_path
                and not allow_source_mismatch
                and Path(declared_path).resolve() != source.resolve()
            ):
                state.err_console.print(
                    hint("warning:"),
                    f"--source {source_str} does not match pipeline "
                    f"input.path {declared_path}; proceeding with --source "
                    "as ground truth (suppress with --allow-source-mismatch).",
                )
        else:
            # No config: synthesize a minimal dict. The runner's
            # residual_pii + policy_validation branches degrade
            # gracefully when relationships + sources + tables are
            # absent (verified against
            # decoy_engine.storm.postmask.runner docstring +
            # tests/unit/storm/test_postmask_runner.py).
            table_name = masked.stem
            config_dict = {
                "version": 1,
                "global_settings": {"seed": 0},
                "sources": {},
                "tables": [],
                "targets": {},
                "relationships": [],
            }

        report = run_storm_post_mask(
            source_frames={table_name: source_df},
            output_frames={table_name: masked_df},
            config=config_dict,
        )

        if out is not None:
            out.write_text(_json.dumps(report, indent=2))

        # Decide exit code based on the report's severity counters.
        fail_count = int(report.get("fail_count") or 0)
        error_count = int(report.get("error_count") or 0)
        exit_code = EXIT_FINDINGS if (fail_count + error_count) > 0 else 0

        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "report integrity",
                    "status": "ok" if exit_code == 0 else "findings",
                    "masked": masked_str,
                    "source": source_str,
                    "report": report,
                },
            )
        elif state.mode is not OutputMode.quiet:
            # Render a 3-row summary table; the per-finding detail
            # lives in the JSON payload (--json or --output).
            table = make_table("Bucket", "Findings", "Severities", title="Storm integrity")
            for bucket in ("residual_pii", "fk_preservation", "policy_validation"):
                findings = report.get(bucket) or []
                if not findings:
                    table.add_row(bucket, "0", success("clean"))
                    continue
                sevs: dict[str, int] = {}
                for f in findings:
                    sev = (f.get("severity") if isinstance(f, dict) else None) or "info"
                    sevs[sev] = sevs.get(sev, 0) + 1
                sev_text = ", ".join(f"{k}:{v}" for k, v in sorted(sevs.items()))
                table.add_row(bucket, str(len(findings)), sev_text)
            state.console.print(table)
            counters = (
                f"pass={report.get('pass_count', 0)}  "
                f"warning={report.get('warning_count', 0)}  "
                f"fail={fail_count}  "
                f"error={error_count}"
            )
            state.console.print(counters)
            if exit_code == 0:
                state.console.print(success("OK"), "no fail or error findings.")
            else:
                state.console.print(
                    risk_high("FINDINGS"),
                    f"{fail_count + error_count} fail/error findings; review the report.",
                )

        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    except typer.Exit:
        raise
    except FileNotFoundError as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "report integrity",
                    "status": "error",
                    "masked": masked_str,
                    "source": source_str,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_USAGE)
    except Exception as exc:
        error_text = str(exc)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "report integrity",
                    "status": "error",
                    "masked": masked_str,
                    "source": source_str,
                    "error": error_text,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), error_text)
            state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback.",
            )
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=EXIT_RUNTIME)


# ---------------------------------------------------------------------------
# CLI: report vault VAULT --config CONFIG  (relocated from `vault info`)
# ---------------------------------------------------------------------------

_VAULT_EPILOG = """\
Examples:

  decoy report vault vault.bin --config pipeline.yaml
    Show entry count, namespaces, and ambiguous-dropped count.

  decoy report vault vault.bin --config pipeline.yaml --json
    Same data as a JSON envelope for scripting.

  decoy report vault vault.bin --config pipeline.yaml --quiet
    Silent mode; exit code 0 = vault opened successfully.

The vault is encrypted under a key derived from the config's seed. The
config passed to --config must be the SAME config (or at least the same
global_settings.seed) used by the `decoy run --vault` call that wrote
the vault, otherwise the decrypt will fail and the command exits 1.

See also: decoy run --vault, decoy unmask --vault.
"""


def _vault(
    vault: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The vault file written by `decoy run --vault`.",
    ),
    config: Path = typer.Option(
        ...,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "The pipeline config the mask run used (must carry the same seed "
            "as the run that wrote the vault)."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout. Errors still go to stderr.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr; exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Inspect a vault file: report entry count, namespaces, and dropped-ambiguous count.

    Opens the vault using the seed derived from the pipeline config. A
    mismatched seed (wrong config) exits 1 with a clear error message.
    Exits 0 on success, 1 on a config/vault/usage error.
    """
    import yaml as _yaml

    state = setup_output(json_, quiet, verbose)

    def _emit_error(message: str, *, hint_text: str | None = None) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "report vault",
                    "status": "error",
                    "vault": str(vault),
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            # markup=False: message is engine text or a user path, not authored
            # markup. Engine install lines such as `pip install 'decoy-engine[vault]'`
            # would otherwise lose the bracketed extra name to Rich's tag parser.
            state.err_console.print(error("error:"), message, markup=False)
            if hint_text:
                state.err_console.print(" ", hint("hint:"), hint_text)

    # Parse config YAML.
    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(sanitize_yaml_error(exc))
        raise typer.Exit(code=EXIT_USAGE)
    if not isinstance(raw, dict):
        _emit_error(
            f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import VaultError, job_seed_for_config, load_vault
    from decoy_engine.plan import PlanCompileError

    # Derive the job seed from the config (fails cleanly for bool/float seeds).
    try:
        job_seed = job_seed_for_config(raw)
    except PlanCompileError as exc:
        from decoy.cli.extras import plan_compile_error_fields

        err_code, message = plan_compile_error_fields(exc)
        _emit_error(f"{err_code}: {message}")
        raise typer.Exit(code=EXIT_USAGE)

    # Open the vault.
    try:
        mapping, ambiguous_dropped = load_vault(str(vault), job_seed)
    except VaultError as exc:
        if getattr(exc, "code", None) == "vault_protocol_version_mismatch":
            _emit_error(
                f"{exc.code}: {exc.message}",
                hint_text=(
                    "the vault was written under a different engine protocol version; "
                    "re-mask under the current engine, or use the engine "
                    "version that wrote the vault."
                ),
            )
        else:
            _emit_error(
                f"{getattr(exc, 'code', type(exc).__name__)}: "
                f"{getattr(exc, 'message', exc)}",
                hint_text=(
                    "the config's seed does not match the vault; "
                    "use the same config (or seed) as the `decoy run --vault` call "
                    "that wrote this vault."
                ),
            )
        raise typer.Exit(code=EXIT_USAGE)

    entries = len(mapping)
    namespaces = sorted({ns for (ns, _) in mapping})

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "report vault",
                "status": "ok",
                "vault": str(vault),
                "entries": entries,
                "namespaces": namespaces,
                "ambiguous_dropped": ambiguous_dropped,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(str(vault)))
    state.console.print(f"  entries:           {entries}")
    state.console.print(f"  namespaces ({len(namespaces)}):   {', '.join(namespaces) or '(none)'}")
    state.console.print(f"  ambiguous dropped: {ambiguous_dropped}")


# ---------------------------------------------------------------------------
# Command registration (continued)
# ---------------------------------------------------------------------------

report_app.command(name="show", epilog=_SHOW_EPILOG)(_show)
report_app.command(name="render", epilog=_RENDER_EPILOG)(_render)
report_app.command(name="verify", epilog=_VERIFY_EPILOG)(_verify)
report_app.command(name="fidelity", epilog=_FIDELITY_EPILOG)(_fidelity)
report_app.command(name="integrity", epilog=_INTEGRITY_EPILOG)(_integrity)
report_app.command(name="diff", epilog=_DIFF_EPILOG)(_diff)
report_app.command(name="vault", epilog=_VAULT_EPILOG)(_vault)

# Public exports
__all__ = [
    "compare_data",
    "compare_manifests",
    "render_html",
    "render_markdown",
    "report_app",
]
