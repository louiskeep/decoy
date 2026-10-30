"""`decoy pre-scan` -- profile a source dataset before any transform runs.

`decoy pre-scan SOURCE` profiles a CSV / Parquet / fixed-width file with the
engine's Pre-scan profiler (`decoy_engine.profile_columns`) and reports dataset
shape, per-field stats, PII candidates, quasi-identifier groups, and a
re-identification risk score. Saved-profile operations are subcommands:
`pre-scan fields SCAN`, `pre-scan show SCAN FIELD`, `pre-scan diff OLD NEW`.

A pre-scan observes the source only. It never establishes that a transformed
output is safe; that is a separate Post-scan claim (`decoy post-scan`).

Two non-negotiable disciplines:

  HONESTY (H4): PII candidates are framed as SUGGESTIONS the user reviews, never
  as authoritative auto-classification. Output says "suggestion -- review
  required" and carries a `pii_note`; it NEVER says "classified as" / "detected
  as" / "is PII".

  PRIVACY (H5): every printed surface is a typed projection minted by
  `decoy.cli._projections` and emitted by the `decoy.cli._value_free` Surface:
  dtype, null rate, distinct count, PII score/bucket, detector ids, policed
  column names. Errors are closed reason codes. This module never prints,
  serializes or formats data itself. The `--output FILE` saved scan is the one
  explicit raw artifact (it keeps the profiler's top values and sentinels).

Reuses the engine's `profile_columns` function. Does NOT reimplement detection.
"""

from __future__ import annotations

import json as _json
import sys
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from decoy.cli import _projections as proj
from decoy.cli import _value_free as vf
from decoy.cli._default_group import make_default_group
from decoy.cli._value_free import LayoutError, Printer, Surface
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode
from decoy.ui.scan_progress import scan_stages
from decoy.ui.theme import accent, code, hint, risk_high, risk_med, success, warn

_PRE_SCAN_GROUP_HELP = (
    "Profile a dataset for PII and re-identification risk. `decoy pre-scan "
    "SOURCE` scans a CSV/Parquet/fixed-width file (shape, field stats, PII "
    "candidates as suggestions, quasi-identifiers, reid risk) and, with "
    "`--output scan.json`, saves the scan. Subcommands operate on a saved "
    "scan: list fields (`fields`), per-field detail (`show`), compare two "
    "scans (`diff`)."
)

_VERBOSE_HELP = "Also print value-free diagnostics on stderr (warning counts, exception type names)."


class SampleStrategy(str, Enum):
    full = "full"
    head = "head"
    random = "random"


class PiiLevel(str, Enum):
    high = "high"
    med = "med"
    low = "low"
    none = "none"


class InputFormat(str, Enum):
    """Explicit input format selector for `scan`.

    When omitted, format is inferred from the file extension:
    - .parquet        -> parquet
    - .fwf / .dat / .fixed / .fw -> fixed-width (requires --layout)
    - anything else   -> delimited (CSV/TSV)

    Fixed-width ALWAYS requires --layout regardless of how the format is
    selected (extension or --format flag). Column boundaries are ambiguous
    without an explicit spec; guessing produces silently wrong profiles.
    """

    delimited = "delimited"
    parquet = "parquet"
    fixed_width = "fixed-width"


# File extensions that map to fixed-width format (require --layout).
_FIXED_WIDTH_EXTENSIONS: frozenset[str] = frozenset({".fwf", ".dat", ".fixed", ".fw"})
# File extensions that map to parquet format.
_PARQUET_EXTENSIONS: frozenset[str] = frozenset({".parquet", ".pq"})

# Suffixes that almost certainly mean "this is raw data, not a saved scan."
_RAW_DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".parquet", ".json.gz", ".jsonl"}


_PRE_SCAN_EPILOG = """\
Examples:

  decoy pre-scan data.csv
    Profile a CSV: row/field counts, PII candidates (as suggestions), reid risk.
    Reads the first 10 000 rows by default (--rows 0 for a full scan).

  decoy pre-scan data.csv --show-fields
    Per-field detail: dtype, null_rate, distinct_count, PII candidate flag.

  decoy pre-scan data.csv --rows 50000 --strategy random
    Sample 50K random rows instead of the first 10 000.

  decoy pre-scan data.csv --output scan.json
    Save the scan to scan.json, then: decoy pre-scan fields scan.json

  decoy pre-scan data.csv --output -
    Stream the scan JSON to stdout for downstream tooling.

  decoy pre-scan records.fwf --layout layout.yaml
    Scan a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

HONESTY: PII candidates are SUGGESTIONS based on pattern matching. They
are NOT authoritative classifications. You review each flagged field and decide
what masking to apply. Decoy never auto-classifies PII.

No raw cell values, paths or layout values appear in any printed output.
Field stats include dtype, null_rate, distinct_count only.

See also: decoy pre-scan fields, decoy pre-scan show, decoy pre-scan diff,
  decoy explain pre-scan, decoy validate.
"""


_FIELDS_EPILOG = """\
Examples:

  decoy pre-scan fields scan.json
    List every field with PII score, bucket, quasi-identifier flag.

  decoy pre-scan fields scan.json --pii high --quasi
    Only fields that are high PII *and* part of a quasi-identifier group.

  decoy pre-scan fields scan.json --json | jq '.fields[].name'
    Pipe just the matching field names somewhere else.

See also: decoy pre-scan, decoy pre-scan show.
"""


_SHOW_EPILOG = """\
Examples:

  decoy pre-scan show scan.json ssn
    Per-field detail card -- type, null rate, distinct count, PII score,
    detector ids, sentinel count, QI membership. Values are withheld.

  decoy pre-scan show scan.json email --json
    The same value-free facts as pre-scan-field/v1 JSON.

  decoy pre-scan data.csv --output - | decoy pre-scan show - ssn
    Pipe a fresh scan straight in.

See also: decoy pre-scan, decoy pre-scan fields.
"""


_DIFF_EPILOG = """\
Examples:

  decoy pre-scan diff baseline.json new.json
    Print field-, PII-, QI-, and risk-level differences between two scans.

  decoy pre-scan diff baseline.json new.json --strict
    Same, but exit 1 on drift (PII bucket bumped up, new high-PII field, or
    new quasi-identifier group). Wire this into CI.

  decoy pre-scan diff baseline.json new.json --json | jq '.drift'
    Boolean drift flag for scripting.

See also: decoy pre-scan, decoy pre-scan fields.
"""


pre_scan_app = typer.Typer(
    name="pre-scan",
    cls=vf.value_free_usage_errors(make_default_group("_pre_scan")),
    help=_PRE_SCAN_GROUP_HELP,
    epilog=_PRE_SCAN_EPILOG,
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Source loaders (format dispatch + sampling).
# ---------------------------------------------------------------------------


def _infer_format(path: Path) -> InputFormat:
    """Infer InputFormat from the file extension.

    Returns fixed_width for known fixed-width extensions, parquet for
    parquet extensions, and delimited for everything else (CSV/TSV).
    """
    suffix = path.suffix.lower()
    if suffix in _PARQUET_EXTENSIONS:
        return InputFormat.parquet
    if suffix in _FIXED_WIDTH_EXTENSIONS:
        return InputFormat.fixed_width
    return InputFormat.delimited


def _parse_layout(layout_path: Path) -> list[dict]:
    """Load a layout spec from a YAML or JSON file.

    Expected shape (YAML or JSON):
        columns:
          - name: field_name
            start: 0      # 0-indexed start position (inclusive)
            width: 10     # column width in characters

    Returns the `columns` list.
    """
    import json as _json_mod

    import yaml as _yaml

    text = layout_path.read_text(encoding="utf-8")
    try:
        data = _yaml.safe_load(text)
    except Exception:
        try:
            data = _json_mod.loads(text)
        except Exception:
            raise LayoutError("not_parseable") from None

    if not isinstance(data, dict) or "columns" not in data:
        raise LayoutError("not_mapping")

    columns = data["columns"]
    if not isinstance(columns, list):
        raise LayoutError("columns_not_list")

    # Errors name the entry index and key only: the rejected value is never echoed.
    for i, col in enumerate(columns):
        if not isinstance(col, dict):
            raise LayoutError("entry_not_mapping", index=i)
        name = col.get("name")
        if not isinstance(name, str) or not name.strip():
            raise LayoutError("name_missing", index=i, key="name")
        for key in ("start", "width"):
            val = col.get(key)
            if val is None:
                raise LayoutError("value_missing", index=i, key=key)
            try:
                int_val = int(val)
            except (TypeError, ValueError):
                raise LayoutError("not_integer", index=i, key=key) from None
            if key == "start" and int_val < 0:
                raise LayoutError("start_negative", index=i, key=key)
            if key == "width" and int_val <= 0:
                raise LayoutError("width_not_positive", index=i, key=key)

    return list(columns)


def _load_csv_with_sampling(path: Path, rows: int | None, strategy: SampleStrategy):
    import pandas as pd

    if strategy is SampleStrategy.full or rows is None:
        return pd.read_csv(path)
    if strategy is SampleStrategy.head:
        return pd.read_csv(path, nrows=rows)
    if strategy is SampleStrategy.random:
        df = pd.read_csv(path)
        if len(df) <= rows:
            return df
        return df.sample(n=rows, random_state=42).reset_index(drop=True)
    return pd.read_csv(path)


def _load_parquet_with_sampling(path: Path, rows: int | None, strategy: SampleStrategy):
    """Load a Parquet file into a DataFrame, respecting the row cap and strategy.

    pyarrow is a core decoy-engine dependency so it is always available.
    For Parquet, 'head' and 'random' sampling work on the in-memory DataFrame
    after loading. Future optimization could use pyarrow row groups for head.
    """
    import pandas as pd

    df = pd.read_parquet(path)
    if rows is None or strategy is SampleStrategy.full or len(df) <= rows:
        return df
    if strategy is SampleStrategy.head:
        return df.head(rows)
    if strategy is SampleStrategy.random:
        return df.sample(n=rows, random_state=42).reset_index(drop=True)
    return df


def _load_fixed_width_with_sampling(
    path: Path,
    layout: list[dict],
    rows: int | None,
    strategy: SampleStrategy,
):
    """Load a fixed-width file into a DataFrame using an explicit layout spec.

    Layout must be a list of dicts with 'name', 'start', and 'width' keys.
    Maps to pandas read_fwf colspecs=(list of (start, start+width)) tuples.
    """
    import pandas as pd

    names = [col["name"] for col in layout]
    colspecs = [(int(col["start"]), int(col["start"]) + int(col["width"])) for col in layout]

    if strategy is SampleStrategy.full or rows is None:
        return pd.read_fwf(path, colspecs=colspecs, names=names, header=None)

    if strategy is SampleStrategy.head:
        return pd.read_fwf(path, colspecs=colspecs, names=names, header=None, nrows=rows)

    # random: load all then sample
    df = pd.read_fwf(path, colspecs=colspecs, names=names, header=None)
    if len(df) <= rows:
        return df
    return df.sample(n=rows, random_state=42).reset_index(drop=True)


def _load_data(
    path: Path,
    fmt: InputFormat,
    layout: list[dict] | None,
    rows: int | None,
    strategy: SampleStrategy,
):
    """Format-dispatching loader for all supported input formats."""
    if fmt is InputFormat.parquet:
        return _load_parquet_with_sampling(path, rows, strategy)
    if fmt is InputFormat.fixed_width:
        if not layout:
            raise ValueError("fixed-width input requires a layout spec")
        return _load_fixed_width_with_sampling(path, layout, rows, strategy)
    # Default: delimited (CSV/TSV)
    return _load_csv_with_sampling(path, rows, strategy)


# ---------------------------------------------------------------------------
# Saved-scan helpers (used by fields/show/diff).
# ---------------------------------------------------------------------------


def _load_scan_dict(scan_path: str) -> dict:
    """Load a pre-scan profile JSON file (or stdin when path is `-`).

    Accepts both shapes `decoy pre-scan` produces -- the bare `to_dict()` written
    to disk by `--output FILE`, and the `{"profile": {...}}` envelope some
    tools wrap it in.
    """
    try:
        raw = sys.stdin.read() if scan_path == "-" else Path(scan_path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # A ValueError, not an OSError: normalise so callers have one unreadable case.
        raise OSError("scan file is not valid UTF-8") from None
    data = _json.loads(raw)
    if not isinstance(data, dict):
        raise _json.JSONDecodeError("scan is not an object", "", 0)
    if "profile" in data and "row_count" not in data and isinstance(data["profile"], dict):
        data = data["profile"]
    return data


def _looks_like_raw_data(scan_path: str) -> bool:
    """True when the path is almost certainly raw data, not a saved scan."""
    if scan_path == "-":
        return False
    p = Path(scan_path)
    suffixes = "".join(p.suffixes).lower()
    if p.suffix.lower() in _RAW_DATA_SUFFIXES or any(
        suffixes.endswith(s) for s in _RAW_DATA_SUFFIXES
    ):
        return True
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(64).lstrip()
    except OSError:
        return False
    return bool(head) and head[0] != "{"


def _load_scan(surface: Surface, scan_path: str) -> dict:
    """Load a saved scan or fail with a closed reason (never the path or parser text)."""
    try:
        return _load_scan_dict(scan_path)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        if _looks_like_raw_data(scan_path):
            surface.fail("scan_is_raw_data")
        if isinstance(exc, FileNotFoundError):
            surface.fail("scan_not_found")
        if isinstance(exc, _json.JSONDecodeError):
            surface.fail("scan_not_json")
        surface.fail("scan_unreadable", exc=exc)


# ---------------------------------------------------------------------------
# Renderers: projection body in, styled text out. No engine object reaches here.
# ---------------------------------------------------------------------------


def _bucket_cell(bucket: str) -> str:
    if bucket == "high":
        return risk_high(bucket)
    if bucket == "med":
        return risk_med(bucket)
    return hint(bucket)


def _score_cell(value: Any) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "-"


def _qi_text(groups: list) -> str:
    return ", ".join("(" + " + ".join(str(m) for m in g) + ")" for g in groups)


def _render_pii_honesty(out: Printer, pii_candidate_count: int) -> None:
    """The profile-honesty framing block (H4): candidates are suggestions."""
    out.line(warn("PII candidates:"), f"{pii_candidate_count} field(s) flagged by pattern matching.")
    out.line(" ", hint("These are SUGGESTIONS for review -- NOT authoritative classifications."))
    out.line(
        " ",
        "Review each flagged field and choose the masking strategy that fits.",
        "Use",
        code("decoy list templates"),
        "to browse available templates.",
    )
    out.line()


def _render_profile(out: Printer, body: Mapping[str, Any]) -> None:
    pii_count = body["pii_candidate_count"]
    facts: list[tuple[str, str]] = [
        ("Rows scanned", f"{body['row_count'] or 0:,} ({body['sample_strategy']})"),
        ("Columns", str(body["field_count"])),
        (
            "PII candidates",
            f"{pii_count} field(s) -- suggestions only, review required"
            if pii_count
            else "none detected",
        ),
        ("Reid risk", str(body["reid_risk_score"])),
    ]
    if body["quasi_identifier_groups"]:
        facts.append(("Quasi-identifiers", _qi_text(body["quasi_identifier_groups"])))
    if body["saved"]:
        facts.append(("Saved", "yes (path not echoed)"))
        next_hint = "decoy pre-scan fields SCAN_FILE"
    else:
        next_hint = "decoy pre-scan SOURCE --output scan.json  (then: decoy pre-scan fields scan.json)"
    out.card("decoy pre-scan", facts, next_hint, "ok")

    fields = body.get("fields")
    if fields is not None:
        out.line()
        out.line(accent(f"Fields ({len(fields)}):"))
        rows = []
        for f in fields:
            cell = ""
            if f["pii_candidate"]:
                cell = "suggestion -- review"
                if f["detector_hits"]:
                    cell += f" [{', '.join(f['detector_hits'])}]"
            null_rate = f["null_rate"]
            rows.append(
                (
                    str(f["name"]),
                    str(f["dtype"]),
                    f"{null_rate:.1%}" if isinstance(null_rate, (int, float)) else "-",
                    str(f["distinct_count"]),
                    cell,
                )
            )
        out.table("Field", "Type", "Null rate", "Distinct", "PII candidate", rows=rows)
        out.line()
        if pii_count:
            _render_pii_honesty(out, pii_count)
    elif pii_count:
        out.line()
        _render_pii_honesty(out, pii_count)
        out.line(hint("Tip:"), "add", code("--show-fields"), "for per-field detail.")


def _render_field_list(out: Printer, body: Mapping[str, Any]) -> None:
    rows = body["fields"]
    if not rows:
        out.line(hint(f"No fields match in the scan (scanned {body['total']})."))
        return
    out.table(
        "Field",
        "PII score",
        "Bucket",
        "QI",
        title=f"Fields in the scan ({len(rows)} of {body['total']})",
        rows=[
            (
                str(r["name"]),
                _score_cell(r["pii_score"]),
                _bucket_cell(r["pii_bucket"]),
                "yes" if r["quasi_identifier"] else "",
            )
            for r in rows
        ],
    )
    out.line(hint("Next:"), code(f"decoy pre-scan show SCAN_FILE {rows[0]['name']}"))


def _render_field_detail(out: Printer, body: Mapping[str, Any]) -> None:
    f = body["field"]
    facts: list[tuple[str, str]] = [
        ("Field", str(f["name"])),
        ("PII score", f"{_score_cell(f['pii_score'])} ({body['pii_bucket']})"),
    ]
    for key, label in (("dtype", "Type"), ("null_rate", "Null rate"), ("distinct_count", "Distinct")):
        if f.get(key) is not None:
            facts.append((label, str(f[key])))
    if f["detector_hits"]:
        facts.append(("Detectors", ", ".join(f["detector_hits"])))
    if body["sentinel_count"]:
        facts.append(("Sentinels", f"{body['sentinel_count']} (values withheld)"))
    if body["quasi_identifier_groups"]:
        facts.append(("Quasi-identifier in", _qi_text(body["quasi_identifier_groups"])))
    if body["values_withheld"]:
        facts.append(("Values", "withheld (top values / sentinels stay in the saved file)"))
    out.card("decoy pre-scan show", facts, "decoy pre-scan fields SCAN_FILE", "ok")


def _render_diff(out: Printer, body: Mapping[str, Any]) -> None:
    summary, changes, drift = body["summary"], body["changes"], body["drift"]
    facts: list[tuple[str, str]] = [
        ("Fields added", str(summary["added"])),
        ("Fields removed", str(summary["removed"])),
        ("PII bucket increased", str(summary["pii_increased"])),
        ("PII bucket decreased", str(summary["pii_decreased"])),
    ]
    delta = summary["reid_risk_delta"]
    if delta is not None:
        facts.append(("Reid risk delta", f"{'+' if delta > 0 else ''}{delta:.2f}"))
    if summary["qi_groups_added"] or summary["qi_groups_removed"]:
        facts.append(("QI groups", f"+{summary['qi_groups_added']} -{summary['qi_groups_removed']}"))
    increased = changes["pii_increased"]
    new_high = [r for r in changes["added"] if r["pii_bucket"] == "high"]
    focus = increased[0]["name"] if increased else (new_high[0]["name"] if new_high else None)
    next_hint = f"decoy pre-scan show NEW_SCAN {focus}" if focus else None
    out.card("decoy pre-scan diff", facts, next_hint, "warn" if drift else "ok")

    def bucket_change(r: Mapping[str, Any], side: str) -> str:
        return f"{r[side + '_bucket']} ({_score_cell(r[side + '_score'])})"

    for key, title in (("pii_increased", "PII bucket increased"), ("pii_decreased", "PII bucket decreased")):
        if changes[key]:
            out.table(
                "Field",
                "Old",
                "New",
                title=title,
                rows=[(str(r["name"]), bucket_change(r, "old"), bucket_change(r, "new")) for r in changes[key]],
            )
    for key, title in (("added", "Fields added"), ("removed", "Fields removed")):
        if changes[key]:
            out.table(
                "Field",
                "PII score",
                "Bucket",
                title=title,
                rows=[
                    (str(r["name"]), _score_cell(r["pii_score"]), _bucket_cell(r["pii_bucket"]))
                    for r in changes[key]
                ],
            )
    for key, title in (
        ("qi_groups_added", "Quasi-identifier groups added"),
        ("qi_groups_removed", "Quasi-identifier groups removed"),
    ):
        if changes[key]:
            out.table("Group", title=title, rows=[(_qi_text([g]),) for g in changes[key]])
    if not drift and not any(summary[k] for k in ("added", "removed", "pii_decreased", "qi_groups_removed")):
        out.line(success("No drift detected."))


# ---------------------------------------------------------------------------
# `decoy pre-scan SOURCE` -- the default command
# ---------------------------------------------------------------------------


@vf.guarded("pre-scan")
def _pre_scan(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to a file to scan (CSV, Parquet, or fixed-width).",
    ),
    show_fields: bool = typer.Option(
        False,
        "--show-fields",
        help="Show per-field detail: dtype, null_rate, distinct_count, PII candidate flag.",
    ),
    rows: int = typer.Option(
        10_000,
        "--rows",
        help=(
            "Limit the scan to the first N rows (a bounded sample). "
            "Use 0 for a full scan of the whole file. Default: 10000."
        ),
    ),
    strategy: SampleStrategy = typer.Option(
        SampleStrategy.head,
        "--strategy",
        help="Sampling strategy when --rows bounds the scan (ignored for --rows 0).",
    ),
    out: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Save the FULL scan JSON to this path: an explicit artifact on disk that "
            "includes raw top values and sentinels, so protect it like the source "
            "(the source path is not recorded in it). Use - to print the value-free "
            "pre-scan-profile/v1 projection to stdout instead (counts, types, rates, "
            "detector ids, policed column names; no cell values). "
            "Without --output nothing is written to disk."
        ),
    ),
    fmt: InputFormat | None = typer.Option(
        None,
        "--format",
        help=(
            "Input format: delimited (CSV/TSV), parquet, or fixed-width. "
            "Default: inferred from file extension. "
            "fixed-width always requires --layout."
        ),
    ),
    layout: Path | None = typer.Option(
        None,
        "--layout",
        exists=False,  # checked manually to give a cleaner error message
        help=(
            "Layout spec (YAML or JSON) for fixed-width input. "
            "Required when format is fixed-width. "
            "Each column needs 'name', 'start' (0-indexed), and 'width'."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the value-free pre-scan-profile/v1 projection as JSON on stdout.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
) -> None:
    """Profile a source dataset: shape, field stats, PII candidates, reid risk.

    Runs the Pre-scan profiler on the source file. PII candidates are surfaced as
    SUGGESTIONS for review -- never as authoritative auto-classifications.
    No raw cell values appear in any printed output (stdout, --json, --output -,
    errors, --verbose); paths, layout values and rejected option values are never
    echoed. Save the scan with `--output scan.json`, then operate on it with
    `decoy pre-scan fields/show/diff`.

    Supported formats: delimited (CSV/TSV, default), parquet, and fixed-width.
    Fixed-width input requires an explicit --layout spec (column boundaries are
    ambiguous without one). Format is inferred from the extension when --format
    is not supplied.
    """
    surface = Surface("pre-scan", json_, quiet, verbose)
    streamed = out is not None and str(out) == "-"

    # `--output -` emits the projection on stdout, so combining it with
    # --json/--quiet would be ambiguous about which stdout contract wins.
    if streamed and surface.mode is not OutputMode.default:
        surface.fail("output_stream_conflict")

    effective_fmt: InputFormat = fmt if fmt is not None else _infer_format(source)
    if effective_fmt is InputFormat.fixed_width and layout is None:
        surface.fail("layout_required")

    layout_columns: list[dict] | None = None
    if layout is not None:
        if not layout.exists():
            surface.fail("layout_not_found")
        try:
            layout_columns = _parse_layout(layout)
        except LayoutError as exc:
            surface.fail("layout_invalid", location=exc.location)
        except Exception as exc:
            surface.fail("layout_invalid", exc=exc)

    # --rows default 10000 bounds the sample; --rows 0 scans the whole file.
    row_cap: int | None = None if rows == 0 else rows
    effective_strategy = SampleStrategy.full if rows == 0 else strategy
    out_path: Path | None = out if (out is not None and not streamed) else None

    try:
        from decoy_engine import profile_columns

        with surface.engine(), scan_stages(
            surface.state, ["Load source", "Profile columns", "Summarize"]
        ) as ms:
            df = _load_data(source, effective_fmt, layout_columns, row_cap, effective_strategy)
            ms.complete()
            # The label is a fixed token: the source file name never enters the profile.
            profile = profile_columns(
                df,
                source_label="source",
                sample_strategy=effective_strategy.value,
                sample_row_cap=row_cap,
            )
            ms.complete()
            scan = profile.to_dict()
            ms.complete()
    except Exception as exc:
        surface.fail("scan_failed", exc=exc)

    if out_path is not None:
        surface.write_saved_scan(out_path, scan)

    projection = proj.profile(
        scan, include_fields=show_fields or streamed, saved=out_path is not None
    )
    if streamed:
        surface.stream(projection)
        return
    surface.emit(projection, status="ok", render=_render_profile)


# ---------------------------------------------------------------------------
# `decoy pre-scan fields SCAN` -- list fields from a saved scan
# ---------------------------------------------------------------------------


@vf.guarded("pre-scan fields")
def _fields(
    scan: str = typer.Argument(..., help="Path to a pre-scan profile JSON, or `-` for stdin."),
    pii: PiiLevel | None = typer.Option(
        None, "--pii", help="Filter to fields whose PII score falls in this bucket."
    ),
    quasi: bool = typer.Option(
        False, "--quasi", help="Only fields that participate in any quasi-identifier group."
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the value-free pre-scan-fields/v1 list (name, PII score/bucket, QI flag).",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
) -> None:
    """List fields from a saved scan, with optional filters.

    Print the fields that matter, filter by PII bucket or quasi-identifier
    membership, pipe the result somewhere else. For per-field detail, see
    `decoy pre-scan show`.
    """
    surface = Surface("pre-scan fields", json_, quiet, verbose)
    data = _load_scan(surface, scan)
    projection = proj.field_list(data, pii=pii.value if pii else None, quasi=quasi)
    surface.emit(projection, status="ok", render=_render_field_list)


# ---------------------------------------------------------------------------
# `decoy pre-scan show SCAN FIELD` -- per-field detail
# ---------------------------------------------------------------------------


@vf.guarded("pre-scan show")
def _show(
    scan: str = typer.Argument(..., help="Path to a pre-scan profile JSON, or `-` for stdin."),
    field: str = typer.Argument(
        ..., help="Field name to inspect (or the field-N label shown for a redacted name)."
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help=(
            "Emit the value-free pre-scan-field/v1 projection: dtype, null rate, "
            "distinct count, PII score/bucket, detector ids, QI membership, sentinel "
            "count. Never top values or sentinel values."
        ),
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
) -> None:
    """Per-field detail from a saved scan (value-free).

    The drill-down view of one field: dtype, null rate, distinct count, PII
    score + bucket, detector ids, quasi-identifier membership and how many
    sentinels were found. Top values and sentinel values are withheld; they stay
    in the saved scan file only. Read-only.
    """
    surface = Surface("pre-scan show", json_, quiet, verbose)
    data = _load_scan(surface, scan)
    matched = proj.find_field(data, field)
    if matched is None:
        surface.fail("field_not_found", suggestion=proj.closest_field(data, field))
    surface.emit(proj.field_detail(data, matched), status="ok", render=_render_field_detail)


# ---------------------------------------------------------------------------
# `decoy pre-scan diff OLD NEW` -- compare two saved scans
# ---------------------------------------------------------------------------


@vf.guarded("pre-scan diff")
def _diff(
    old: str = typer.Argument(..., help="Path to the older pre-scan profile JSON, or `-` for stdin."),
    new: str = typer.Argument(..., help="Path to the newer pre-scan profile JSON, or `-` for stdin."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit 1 on drift -- any PII bucket bumped up, any new high-PII field, or any new quasi-identifier group.",
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit the value-free pre-scan-diff/v1 projection as JSON."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help=_VERBOSE_HELP),
) -> None:
    """Compare two scans -- catch schema, PII, and risk drift.

    Designed for CI: run `decoy pre-scan diff baseline.json new.json --strict`
    on every PR to fail the build when a column's PII bucket goes up, a new
    high-PII field appears, or a new quasi-identifier group forms. Read-only
    -- the scans are JSON; raw data never enters the CLI.
    """
    surface = Surface("pre-scan diff", json_, quiet, verbose)
    if old == "-" and new == "-":
        surface.fail("diff_two_stdin")
    projection = proj.scan_diff(_load_scan(surface, old), _load_scan(surface, new))
    surface.emit(projection, status="ok", render=_render_diff)
    if strict and projection.body["drift"]:
        raise typer.Exit(code=EXIT_USAGE)


# The hidden default command: `decoy pre-scan SOURCE` (no subcommand) routes here
# via the shared default-command group. Hidden so it stays out of help / the
# generated reference / completion, while the group can still dispatch to it.
pre_scan_app.command(name="_pre_scan", hidden=True, epilog=_PRE_SCAN_EPILOG)(_pre_scan)
pre_scan_app.command(name="fields", epilog=_FIELDS_EPILOG)(_fields)
pre_scan_app.command(name="show", epilog=_SHOW_EPILOG)(_show)
pre_scan_app.command(name="diff", epilog=_DIFF_EPILOG)(_diff)

SCAN_EPILOG = _PRE_SCAN_EPILOG

__all__ = ["SCAN_EPILOG", "pre_scan_app"]
