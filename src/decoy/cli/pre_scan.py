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

  PRIVACY (H5): every command runs inside the `decoy.cli._boundary` process
  boundary, and every printed surface is a typed projection minted by
  `decoy.cli._projections`: dtype, null rate, distinct count, PII score/bucket,
  detector ids, policed column names. No cell values, file paths, table names
  or free-text diagnostics; policed schema identifiers remain. Errors are
  closed reason codes. This module cannot print, write or serialize: the
  sentry pins its imports and attributes. The `--output FILE` saved scan is the
  one explicit raw artifact: it writes the full scan profile including sample
  top values and sentinels (owner-only, mode 0600).

Reuses the engine's `profile_columns` function. Does NOT reimplement detection.
"""

from __future__ import annotations

import json as _json
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from decoy.cli import _boundary as bd
from decoy.cli import _projections as proj
from decoy.cli import _value_free as vf
from decoy.cli._boundary import Fragment, Printer, Surface
from decoy.cli._default_group import make_default_group
from decoy.cli._value_free import LayoutError
from decoy.cli.exit_codes import EXIT_USAGE

_PRE_SCAN_GROUP_HELP = (
    "Profile a dataset for PII and re-identification risk. `decoy pre-scan "
    "SOURCE` scans a CSV/Parquet/fixed-width file (shape, field stats, PII "
    "candidates as suggestions, quasi-identifiers, reid risk) and, with "
    "`--output scan.json`, saves the scan. Subcommands operate on a saved "
    "scan: list fields (`fields`), per-field detail (`show`), compare two "
    "scans (`diff`). Printed output carries no cell values, paths, table names "
    "or free-text diagnostics; policed column names are shown. WARNING: "
    "`--output FILE` writes the full scan profile including sample top values "
    "and sentinels (owner-only, mode 0600); use `--json` for the value-free "
    "projection."
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
    WARNING: writes the full scan profile including sample top values and
    sentinels (owner-only, mode 0600). Protect it like the source.

  decoy pre-scan data.csv --output -
    Stream the scan JSON to stdout for downstream tooling.

  decoy pre-scan records.fwf --layout layout.yaml
    Scan a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

HONESTY: PII candidates are SUGGESTIONS based on pattern matching. They
are NOT authoritative classifications. You review each flagged field and decide
what masking to apply. Decoy never auto-classifies PII.

No cell values, paths, table names, layout values or free-text diagnostics
appear in any printed output; policed column names (at most 64 characters of
[A-Za-z0-9_ .-]) do. Field stats include dtype, null_rate, distinct_count only.

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
    cls=bd.value_free_group(make_default_group("_pre_scan"), "pre-scan"),
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


def _load_scan_dict(surface: Surface, scan_path: str) -> dict:
    """Load a pre-scan profile JSON file (or stdin when path is `-`).

    Accepts both shapes `decoy pre-scan` produces -- the bare `to_dict()` written
    to disk by `--output FILE`, and the `{"profile": {...}}` envelope some
    tools wrap it in.
    """
    try:
        raw = surface.read_text(scan_path)
    except UnicodeDecodeError:
        # A ValueError, not an OSError: normalise so callers have one unreadable case.
        raise OSError("scan file is not valid UTF-8") from None
    data = _json.loads(raw)
    if not isinstance(data, dict):
        raise _json.JSONDecodeError("scan is not an object", "", 0)
    if "profile" in data and "row_count" not in data and isinstance(data["profile"], dict):
        data = data["profile"]
    return data


def _looks_like_raw_data(surface: Surface, scan_path: str) -> bool:
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
        head = surface.peek_text(p, 64).lstrip()
    except OSError:
        return False
    return bool(head) and head[0] != "{"


def _load_scan(surface: Surface, scan_path: str) -> dict:
    """Load a saved scan or fail with a closed reason (never the path or parser text)."""
    try:
        return _load_scan_dict(surface, scan_path)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        if _looks_like_raw_data(surface, scan_path):
            surface.fail("scan_is_raw_data")
        if isinstance(exc, FileNotFoundError):
            surface.fail("scan_not_found")
        if isinstance(exc, _json.JSONDecodeError):
            surface.fail("scan_not_json")
        surface.fail("scan_unreadable", exc=exc)


# ---------------------------------------------------------------------------
# Renderers: pure functions of (Printer, projection body). The sentry checks
# that they only call `p` methods, literal templates and each other.
# ---------------------------------------------------------------------------


def _bucket_cell(p: Printer, bucket: Any) -> Fragment:
    if bucket == "high":
        return p.t("{}", bucket, style="risk_high")
    if bucket == "med":
        return p.t("{}", bucket, style="risk_med")
    return p.t("{}", bucket, style="hint")


def _score_cell(p: Printer, value: Any) -> Fragment:
    return p.t("{:.2f}", value) if isinstance(value, (int, float)) else p.t("-")


def _qi_text(p: Printer, groups: Any) -> Fragment:
    return p.join(", ", [p.cat(p.t("("), p.join(" + ", g), p.t(")")) for g in groups])


def _render_pii_honesty(p: Printer, pii_candidate_count: Any) -> None:
    """The profile-honesty framing block (H4): candidates are suggestions."""
    p.line(
        p.t("PII candidates:", style="warn"),
        p.t("{} field(s) flagged by pattern matching.", pii_candidate_count),
    )
    p.line(
        p.t(" "),
        p.t("These are SUGGESTIONS for review -- NOT authoritative classifications.", style="hint"),
    )
    p.line(
        p.t(" "),
        p.t("Review each flagged field and choose the masking strategy that fits."),
        p.t("Use"),
        p.t("decoy list templates", style="code"),
        p.t("to browse available templates."),
    )
    p.line()


def _render_profile(p: Printer, body: Mapping[str, Any]) -> None:
    pii_count = body["pii_candidate_count"]
    facts = [
        (p.t("Rows scanned"), p.t("{:,} ({})", body["row_count"] or 0, body["sample_strategy"])),
        (p.t("Columns"), body["field_count"]),
        (
            p.t("PII candidates"),
            p.t("{} field(s) -- suggestions only, review required", pii_count)
            if pii_count
            else p.t("none detected"),
        ),
        (p.t("Reid risk"), body["reid_risk_score"]),
    ]
    if body["quasi_identifier_groups"]:
        facts.append((p.t("Quasi-identifiers"), _qi_text(p, body["quasi_identifier_groups"])))
    if body["saved"]:
        facts.append((p.t("Saved"), p.t("yes (path not echoed)")))
        next_hint = p.t("decoy pre-scan fields SCAN_FILE")
    else:
        next_hint = p.t(
            "decoy pre-scan SOURCE --output scan.json  (then: decoy pre-scan fields scan.json)"
        )
    p.card("decoy pre-scan", facts, next_hint, "ok")

    fields = body.get("fields")
    if fields is not None:
        p.line()
        p.line(p.t("Fields ({}):", len(fields), style="accent"))
        rows = []
        for f in fields:
            cell = p.t("")
            if f["pii_candidate"]:
                cell = p.t("suggestion -- review")
                if f["detector_hits"]:
                    cell = p.cat(cell, p.t(" ["), p.join(", ", f["detector_hits"]), p.t("]"))
            null_rate = f["null_rate"]
            rows.append(
                (
                    f["name"],
                    f["dtype"],
                    p.t("{:.1%}", null_rate) if isinstance(null_rate, (int, float)) else p.t("-"),
                    f["distinct_count"],
                    cell,
                )
            )
        p.table("Field", "Type", "Null rate", "Distinct", "PII candidate", rows=rows)
        p.line()
        if pii_count:
            _render_pii_honesty(p, pii_count)
    elif pii_count:
        p.line()
        _render_pii_honesty(p, pii_count)
        p.line(p.t("Tip:", style="hint"), p.t("add"), p.t("--show-fields", style="code"), p.t("for per-field detail."))


def _render_field_list(p: Printer, body: Mapping[str, Any]) -> None:
    rows = body["fields"]
    if not rows:
        p.line(p.t("No fields match in the scan (scanned {}).", body["total"], style="hint"))
        return
    p.table(
        "Field",
        "PII score",
        "Bucket",
        "QI",
        title=p.t("Fields in the scan ({} of {})", len(rows), body["total"]),
        rows=[
            (
                r["name"],
                _score_cell(p, r["pii_score"]),
                _bucket_cell(p, r["pii_bucket"]),
                p.t("yes") if r["quasi_identifier"] else p.t(""),
            )
            for r in rows
        ],
    )
    p.line(p.t("Next:", style="hint"), p.t("decoy pre-scan show SCAN_FILE {}", rows[0]["name"], style="code"))


def _render_field_detail(p: Printer, body: Mapping[str, Any]) -> None:
    f = body["field"]
    facts = [
        (p.t("Field"), f["name"]),
        (p.t("PII score"), p.cat(_score_cell(p, f["pii_score"]), p.t(" ({})", body["pii_bucket"]))),
    ]
    if f.get("dtype") is not None:
        facts.append((p.t("Type"), f["dtype"]))
    if f.get("null_rate") is not None:
        facts.append((p.t("Null rate"), f["null_rate"]))
    if f.get("distinct_count") is not None:
        facts.append((p.t("Distinct"), f["distinct_count"]))
    if f["detector_hits"]:
        facts.append((p.t("Detectors"), p.join(", ", f["detector_hits"])))
    if body["sentinel_count"]:
        facts.append((p.t("Sentinels"), p.t("{} (values withheld)", body["sentinel_count"])))
    if body["quasi_identifier_groups"]:
        facts.append((p.t("Quasi-identifier in"), _qi_text(p, body["quasi_identifier_groups"])))
    if body["values_withheld"]:
        facts.append(
            (p.t("Values"), p.t("withheld (top values / sentinels stay in the saved file)"))
        )
    p.card("decoy pre-scan show", facts, p.t("decoy pre-scan fields SCAN_FILE"), "ok")


def _bucket_change(p: Printer, bucket: Any, score: Any) -> Fragment:
    return p.cat(p.t("{} (", bucket), _score_cell(p, score), p.t(")"))


def _change_rows(p: Printer, changes: Any) -> list[tuple[Any, Fragment, Fragment]]:
    return [
        (
            r["name"],
            _bucket_change(p, r["old_bucket"], r["old_score"]),
            _bucket_change(p, r["new_bucket"], r["new_score"]),
        )
        for r in changes
    ]


def _field_rows(p: Printer, changes: Any) -> list[tuple[Any, Fragment, Fragment]]:
    return [
        (r["name"], _score_cell(p, r["pii_score"]), _bucket_cell(p, r["pii_bucket"]))
        for r in changes
    ]


def _render_diff(p: Printer, body: Mapping[str, Any]) -> None:
    summary, changes, drift = body["summary"], body["changes"], body["drift"]
    facts = [
        (p.t("Fields added"), summary["added"]),
        (p.t("Fields removed"), summary["removed"]),
        (p.t("PII bucket increased"), summary["pii_increased"]),
        (p.t("PII bucket decreased"), summary["pii_decreased"]),
    ]
    delta = summary["reid_risk_delta"]
    if delta is not None:
        facts.append(
            (p.t("Reid risk delta"), p.t("{:+.2f}", delta) if delta > 0 else p.t("{:.2f}", delta))
        )
    if summary["qi_groups_added"] or summary["qi_groups_removed"]:
        facts.append(
            (p.t("QI groups"), p.t("+{} -{}", summary["qi_groups_added"], summary["qi_groups_removed"]))
        )
    increased = changes["pii_increased"]
    new_high = [r for r in changes["added"] if r["pii_bucket"] == "high"]
    focus = increased[0]["name"] if increased else (new_high[0]["name"] if new_high else None)
    next_hint = p.t("decoy pre-scan show NEW_SCAN {}", focus) if focus else None
    p.card("decoy pre-scan diff", facts, next_hint, "warn" if drift else "ok")

    if changes["pii_increased"]:
        p.table(
            "Field", "Old", "New", title=p.t("PII bucket increased"),
            rows=_change_rows(p, changes["pii_increased"]),
        )  # fmt: skip
    if changes["pii_decreased"]:
        p.table(
            "Field", "Old", "New", title=p.t("PII bucket decreased"),
            rows=_change_rows(p, changes["pii_decreased"]),
        )  # fmt: skip
    if changes["added"]:
        p.table(
            "Field", "PII score", "Bucket", title=p.t("Fields added"),
            rows=_field_rows(p, changes["added"]),
        )  # fmt: skip
    if changes["removed"]:
        p.table(
            "Field", "PII score", "Bucket", title=p.t("Fields removed"),
            rows=_field_rows(p, changes["removed"]),
        )  # fmt: skip
    if changes["qi_groups_added"]:
        p.table(
            "Group", title=p.t("Quasi-identifier groups added"),
            rows=[(_qi_text(p, [g]),) for g in changes["qi_groups_added"]],
        )  # fmt: skip
    if changes["qi_groups_removed"]:
        p.table(
            "Group", title=p.t("Quasi-identifier groups removed"),
            rows=[(_qi_text(p, [g]),) for g in changes["qi_groups_removed"]],
        )  # fmt: skip
    quiet_summary = not any(
        summary[k] for k in ("added", "removed", "pii_decreased", "qi_groups_removed")
    )
    if not drift and quiet_summary:
        p.line(p.t("No drift detected.", style="success"))


# ---------------------------------------------------------------------------
# `decoy pre-scan SOURCE` -- the default command
# ---------------------------------------------------------------------------


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
            "WARNING: writes the full scan profile including sample top values and "
            "sentinels to this path (owner-only, mode 0600; the source path is not "
            "recorded). Protect it like the source. Use - to print the value-free "
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
    No cell values, paths, table names or free-text diagnostics appear in any
    printed output (stdout, --json, --output -, errors, --verbose); policed
    column names do. Layout values and rejected option values are never echoed.
    `--output scan.json` writes the full scan profile including sample top values
    and sentinels (mode 0600); operate on it with `decoy pre-scan fields/show/diff`.

    Supported formats: delimited (CSV/TSV, default), parquet, and fixed-width.
    Fixed-width input requires an explicit --layout spec (column boundaries are
    ambiguous without one). Format is inferred from the extension when --format
    is not supplied.
    """
    surface = bd.surface("pre-scan", json_=json_, quiet=quiet, verbose=verbose)
    streamed = out is not None and str(out) == "-"

    # `--output -` emits the projection on stdout, so combining it with
    # --json/--quiet would be ambiguous about which stdout contract wins.
    if streamed and surface.mode != "default":
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

        with surface.progress(
            vf.StageId.LOAD_SOURCE, vf.StageId.PROFILE_COLUMNS, vf.StageId.SUMMARIZE
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
    surface = bd.surface("pre-scan fields", json_=json_, quiet=quiet, verbose=verbose)
    data = _load_scan(surface, scan)
    projection = proj.field_list(data, pii=pii.value if pii else None, quasi=quasi)
    surface.emit(projection, status="ok", render=_render_field_list)


# ---------------------------------------------------------------------------
# `decoy pre-scan show SCAN FIELD` -- per-field detail
# ---------------------------------------------------------------------------


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
    surface = bd.surface("pre-scan show", json_=json_, quiet=quiet, verbose=verbose)
    data = _load_scan(surface, scan)
    matched = proj.find_field(data, field)
    if matched is None:
        surface.fail("field_not_found", suggestion=proj.closest_field(data, field))
    surface.emit(proj.field_detail(data, matched), status="ok", render=_render_field_detail)


# ---------------------------------------------------------------------------
# `decoy pre-scan diff OLD NEW` -- compare two saved scans
# ---------------------------------------------------------------------------


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
    surface = bd.surface("pre-scan diff", json_=json_, quiet=quiet, verbose=verbose)
    if old == "-" and new == "-":
        surface.fail("diff_two_stdin")
    projection = proj.scan_diff(_load_scan(surface, old), _load_scan(surface, new))
    surface.emit(projection, status="ok", render=_render_diff)
    if strict and projection.body["drift"]:
        raise typer.Exit(code=EXIT_USAGE)


# The hidden default command: `decoy pre-scan SOURCE` (no subcommand) routes here
# via the shared default-command group. Hidden so it stays out of help / the
# generated reference / completion, while the group can still dispatch to it.
_CMD = bd.ValueFreeCommand
pre_scan_app.command(name="_pre_scan", hidden=True, epilog=_PRE_SCAN_EPILOG, cls=_CMD)(_pre_scan)
pre_scan_app.command(name="fields", epilog=_FIELDS_EPILOG, cls=_CMD)(_fields)
pre_scan_app.command(name="show", epilog=_SHOW_EPILOG, cls=_CMD)(_show)
pre_scan_app.command(name="diff", epilog=_DIFF_EPILOG, cls=_CMD)(_diff)

SCAN_EPILOG = _PRE_SCAN_EPILOG

__all__ = ["SCAN_EPILOG", "pre_scan_app"]
