"""`decoy scan` -- one "look at my data" verb (merges `profile` + `storm analyze`).

`decoy scan SOURCE` profiles a CSV / Parquet / fixed-width file with the engine's
STORM (Statistical Top-down Risk Mapping) detector and reports dataset shape,
per-field stats, PII candidates, quasi-identifier groups, and a re-identification
risk score. Saved-scan operations are subcommands: `scan fields SCAN`,
`scan show SCAN FIELD`, `scan diff OLD NEW`.

This command is the S3a merge of the former top-level `profile` command and the
`storm analyze` verb. It keeps BOTH commands' capabilities while preserving the
former profile command's two
non-negotiable disciplines:

  HONESTY (H4): PII candidates are framed as SUGGESTIONS the user reviews, never
  as authoritative auto-classification. Output says "suggestion -- review
  required" and carries a `pii_note`; it NEVER says "classified as" / "detected
  as" / "is PII". The user picks the PII type per field; auto-classification is
  abandoned by design.

  PRIVACY (H5): the inline / `--show-fields` field rendering uses the
  privacy-safe `safe_field_record` -- dtype, null_rate, distinct_count,
  pii_score, detector ids ONLY. It NEVER includes top_values, mode/min/max, or
  any aggregate that could expose raw cell data. `--output` writes the
  value-free `scan-set/v1` core as well.

Reuses the engine's `profile_columns` function. Does NOT reimplement detection.
"""

from __future__ import annotations

import difflib
import json as _json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import typer

from decoy.cli._default_group import make_default_group
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io._scan_set import ScanSetFormatError, load_scan_set, select_table
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import code, error, hint, risk_high, risk_med, success

_SCAN_GROUP_HELP = (
    "Profile a dataset for PII and re-identification risk. `decoy scan "
    "SOURCES...` scans CSV/Parquet/fixed-width files, one table each (shape, "
    "field stats, PII candidates as suggestions, quasi-identifiers, reid "
    "risk) and, with `--output scan.json`, saves the value-free scan. "
    "Subcommands operate on a saved scan: list fields (`fields`), per-field "
    "detail (`show`), compare two scans (`diff`)."
)


# PII score threshold to surface a field as a candidate. Mirrors the engine's
# STORM internal threshold (>=0.6 is a "PII candidate" / "high" bucket).
_PII_CANDIDATE_THRESHOLD = 0.6


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

_BUCKET_RANK: dict[str, int] = {"none": 0, "low": 1, "med": 2, "high": 3}

# Suffixes that almost certainly mean "this is raw data, not a saved scan."
# Used by `_emit_load_error` to swap the generic JSON parse hint for a
# specific "scan it first" suggestion.
_RAW_DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".parquet", ".json.gz", ".jsonl"}


_SCAN_EPILOG = """\
Examples:

  decoy scan data.csv --has-header
    Profile a CSV: row/field counts, PII candidates (as suggestions), reid risk.
    A CSV always needs --has-header or --no-header: scan never guesses.
    Reads the first 10 000 rows by default (--rows 0 for a full scan).

  decoy scan customers.csv orders.csv --has-header
    Scan several files in one run: one table each, named from the file stem.

  decoy scan raw.csv --no-header --column-names id,name,email
    A headerless CSV: row 1 is data, the names come from you.

  decoy scan data.csv --has-header --show-fields
    Per-field detail: dtype, null_rate, distinct_count, PII candidate flag.

  decoy scan data.csv --has-header --rows 50000 --strategy random
    Sample 50K random rows instead of the first 10 000.

  decoy scan data.csv --has-header --output scan.json
    Save the value-free scan to scan.json, then: decoy scan fields scan.json

  decoy scan data.csv --has-header --output -
    Stream the scan JSON to stdout for downstream tooling.

  decoy scan records.fwf --layout layout.yaml
    Scan a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

HONESTY: PII candidates are SUGGESTIONS based on STORM pattern matching. They
are NOT authoritative classifications. You review each flagged field and decide
what masking to apply. Decoy never auto-classifies PII.

No raw cell values appear in the inline output or in --output. Field stats
include dtype, null_rate, distinct_count only.

See also: decoy scan fields, decoy scan show, decoy scan diff,
  decoy explain storm, decoy validate.
"""


_FIELDS_EPILOG = """\
Examples:

  decoy scan fields scan.json
    List every field with PII score, bucket, quasi-identifier flag.

  decoy scan fields scan.json --pii high --quasi
    Only fields that are high PII *and* part of a quasi-identifier group.

  decoy scan fields scan.json --json | jq '.fields[].name'
    Pipe just the matching field names somewhere else.

See also: decoy scan, decoy scan show.
"""


_SHOW_EPILOG = """\
Examples:

  decoy scan show scan.json ssn
    Per-field detail card -- type, PII score, detectors, QI. No cell values.

  decoy scan show scan.json email --json
    Same data as a structured JSON envelope.

  decoy scan data.csv --has-header --output - | decoy scan show - ssn
    Pipe a fresh scan straight in.

See also: decoy scan, decoy scan fields.
"""


_DIFF_EPILOG = """\
Examples:

  decoy scan diff baseline.json new.json
    Print field-, PII-, QI-, and risk-level differences between two scans.

  decoy scan diff baseline.json new.json --strict
    Same, but exit 1 on drift (PII bucket bumped up, new high-PII field, or
    new quasi-identifier group). Wire this into CI.

  decoy scan diff baseline.json new.json --json | jq '.drift'
    Boolean drift flag for scripting.

See also: decoy scan, decoy scan fields.
"""


scan_app = typer.Typer(
    name="scan",
    cls=make_default_group("_scan"),
    help=_SCAN_GROUP_HELP,
    epilog=_SCAN_EPILOG,
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Source loaders (format dispatch + sampling). Moved from storm.py with `scan`.
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
        data = _json_mod.loads(text)

    if not isinstance(data, dict) or "columns" not in data:
        raise ValueError(
            f"Layout file {layout_path.name} must be a mapping with a 'columns' key. "
            "Each column must have 'name', 'start', and 'width'."
        )

    columns = data["columns"]
    if not isinstance(columns, list):
        raise ValueError(
            f"Layout file {layout_path.name}: 'columns' must be a list of column dicts, "
            f"got {type(columns).__name__}. Each column needs a string 'name' and integer 'start'/'width'."
        )

    for i, col in enumerate(columns):
        if not isinstance(col, dict):
            raise ValueError(
                f"layout column {i}: expected a dict, got {type(col).__name__} - "
                "each column needs a string 'name' and integer 'start'/'width'."
            )
        name = col.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"layout column {i} ({name!r}): missing or empty 'name' - "
                "each column needs a string 'name' and integer 'start'/'width'."
            )
        for key in ("start", "width"):
            val = col.get(key)
            if val is None:
                raise ValueError(
                    f"layout column {i} ({name!r}): missing '{key}' - "
                    "each column needs a string 'name' and integer 'start'/'width'."
                )
            try:
                int_val = int(val)
            except (TypeError, ValueError):
                raise ValueError(
                    f"layout column {i} ({name!r}): '{key}' must be an integer, got {val!r} - "
                    "each column needs a string 'name' and integer 'start'/'width'."
                )
            if key == "start" and int_val < 0:
                raise ValueError(
                    f"layout column {i} ({name!r}): 'start' must be >= 0, got {int_val} - "
                    "each column needs a string 'name' and integer 'start'/'width'."
                )
            if key == "width" and int_val <= 0:
                raise ValueError(
                    f"layout column {i} ({name!r}): 'width' must be > 0, got {int_val} - "
                    "each column needs a string 'name' and integer 'start'/'width'."
                )

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
    from decoy.cli._sources import read_file

    df = read_file(path, "parquet", None, table=path.stem)
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
            raise ValueError(
                f"Fixed-width input requires --layout: column boundaries in {path.name} "
                "are ambiguous without an explicit layout spec. "
                "Run: decoy scan <file> --layout <layout.yaml>"
            )
        return _load_fixed_width_with_sampling(path, layout, rows, strategy)
    # Default: delimited (CSV/TSV)
    return _load_csv_with_sampling(path, rows, strategy)


# ---------------------------------------------------------------------------
# Saved-scan helpers (used by fields/show/diff). Moved from storm.py.
# ---------------------------------------------------------------------------


def _pii_bucket(score: float | None) -> str:
    """Same buckets as the `scan` card uses (>=0.6 PII candidate count)."""
    if score is None:
        return "none"
    if score >= 0.6:
        return "high"
    if score >= 0.3:
        return "med"
    if score > 0:
        return "low"
    return "none"


def _bucket_rank(bucket: str) -> int:
    return _BUCKET_RANK.get(bucket, 0)


def _is_quasi(name: str, qi_groups: list) -> bool:
    return any(name in g for g in qi_groups)


def _canon_qi(group: list) -> tuple[str, ...]:
    """Canonical, hashable form of a QI group for set comparison."""
    return tuple(sorted(str(x) for x in group))


def _looks_like_raw_data(scan_path: str) -> bool:
    """True when the path is almost certainly raw data, not a saved scan.

    Suffix check first (cheap + decisive); content sniff as a fallback for
    paths without a recognised suffix. Stays lenient -- only triggers the
    'scan it first' hint when we're confident.
    """
    if scan_path == "-":
        return False
    p = Path(scan_path)
    suffix = p.suffix.lower()
    if suffix in _RAW_DATA_SUFFIXES:
        return True
    suffixes = "".join(p.suffixes).lower()
    if any(suffixes.endswith(s) for s in _RAW_DATA_SUFFIXES):
        return True
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(64).lstrip()
    except OSError:
        return False
    return bool(head) and head[0] != "{"


def _emit_load_error(
    state: OutputState, scan: str, exc: Exception, command_name: str
) -> None:
    """Friendly error UX when a scan path won't load.

    Detects three cases: missing file, raw-data-mistaken-for-scan, and
    malformed JSON. Each gets a tailored hint per CLI_UX_GUIDE section 9
    (cause line + verb-sentence hint).
    """
    raw_data = _looks_like_raw_data(scan)
    if raw_data:
        label = Path(scan).name
        message = f"{label} looks like raw data, not a STORM scan JSON."
        scan_cmd = f"decoy scan {scan} --has-header --output scan.json"
    elif isinstance(exc, FileNotFoundError):
        message = f"could not open {scan}: file not found."
        scan_cmd = None
    elif isinstance(exc, _json.JSONDecodeError):
        message = f"could not parse {scan} as JSON ({exc.msg})."
        scan_cmd = None
    else:
        message = str(exc)
        scan_cmd = None

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": command_name,
                "status": "error",
                "scan": scan,
                "error": message,
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), message)
        if scan_cmd is not None:
            state.err_console.print(
                " ", hint("hint:"), "scan it first:", code(scan_cmd),
            )
        else:
            state.err_console.print(
                " ", hint("hint:"),
                "pass the JSON file produced by",
                code("decoy scan --output scan.json"),
            )


_TABLE_HELP = "Table to read when the saved scan holds more than one."


_LOAD_ERRORS = (ScanSetFormatError, FileNotFoundError, _json.JSONDecodeError, OSError)


def _read_table(scan: str, table: str | None) -> dict:
    """A saved scan's one table (raises one of `_LOAD_ERRORS`)."""
    return select_table(load_scan_set(scan), table)


# ---------------------------------------------------------------------------
# `decoy scan SOURCE` -- the default command (merges profile + storm analyze)
# ---------------------------------------------------------------------------


def _scan(
    sources: list[Path] = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Files to scan (CSV, Parquet, or fixed-width), one table each.",
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
            "Save the value-free scan JSON to this path. Use - for stdout. "
            "Without --output nothing is written to disk."
        ),
    ),
    fmt: InputFormat | None = typer.Option(
        None,
        "--format",
        help=(
            "Input format: delimited (CSV/TSV), parquet, or fixed-width. "
            "Default: inferred from file extension. One file only. "
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
    has_header: bool | None = typer.Option(
        None,
        "--has-header/--no-header",
        help=(
            "Required for every CSV: does row 1 hold the column names? "
            "With --no-header, row 1 is data and --column-names supplies the names."
        ),
    ),
    column_names: str | None = typer.Option(
        None,
        "--column-names",
        help="Comma-separated column names for one headerless CSV (needs --no-header).",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout instead of the styled card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Profile source files: shape, field stats, PII candidates, reid risk.

    Runs STORM detection on each file, one table per file. PII candidates are
    surfaced as SUGGESTIONS for review, never as authoritative classifications.
    No raw cell values appear in the inline output or in `--output`. Save the
    scan with `--output scan.json`, then use `decoy scan fields/show/diff`.

    A CSV needs `--has-header` or `--no-header`: scan never guesses. Fixed-width
    input requires an explicit --layout spec. Format is inferred from the
    extension when --format is not supplied.
    """
    from decoy.cli.scanning._multi import run_scan

    run_scan(
        setup_output(json_, quiet, verbose),
        sources=sources,
        show_fields=show_fields,
        rows=rows,
        strategy=strategy.value,
        out=out,
        fmt=fmt.value if fmt is not None else None,
        layout=layout,
        has_header=has_header,
        column_names=column_names,
    )


# ---------------------------------------------------------------------------
# `decoy scan fields SCAN` -- list fields from a saved scan (was the storm verb)
# ---------------------------------------------------------------------------


def _fields(
    scan: str = typer.Argument(
        ..., help="Path to a STORM scan JSON, or `-` for stdin."
    ),
    pii: PiiLevel | None = typer.Option(
        None, "--pii",
        help="Filter to fields whose PII score falls in this bucket.",
    ),
    quasi: bool = typer.Option(
        False, "--quasi",
        help="Only fields that participate in any quasi-identifier group.",
    ),
    table: str | None = typer.Option(None, "--table", help=_TABLE_HELP),
    json_: bool = typer.Option(
        False, "--json", help="Emit the filtered field list as JSON to stdout."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List fields from a saved scan, with optional filters.

    Print the fields that matter, filter by PII bucket or quasi-identifier
    membership, pipe the result somewhere else. For per-field detail, see
    `decoy scan show`.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        data = _read_table(scan, table)
    except _LOAD_ERRORS as exc:
        _emit_load_error(state, scan, exc, "scan fields")
        raise typer.Exit(code=EXIT_USAGE) from None

    fields = data.get("fields", [])
    qi_groups = data.get("quasi_identifier_groups", [])
    total = len(fields)

    if pii is not None:
        fields = [f for f in fields if _pii_bucket(f.get("pii_score")) == pii.value]
    if quasi:
        fields = [f for f in fields if _is_quasi(f.get("name", ""), qi_groups)]

    rows = [
        {
            "name": f.get("name"),
            "pii_score": f.get("pii_score"),
            "pii_bucket": _pii_bucket(f.get("pii_score")),
            "quasi_identifier": _is_quasi(f.get("name", ""), qi_groups),
        }
        for f in fields
    ]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "scan fields",
                "status": "ok",
                "scan": scan,
                "matched": len(rows),
                "total": total,
                "fields": rows,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    label = Path(scan).name if scan != "-" else "stdin"
    if not rows:
        state.console.print(hint(f"No fields match in {label} (scanned {total})."))
        return

    table = make_table(
        "Field", "PII score", "Bucket", "QI",
        title=f"Fields in {label} ({len(rows)} of {total})",
    )
    for r in rows:
        bucket = r["pii_bucket"]
        if bucket == "high":
            bucket_cell = risk_high(bucket)
        elif bucket == "med":
            bucket_cell = risk_med(bucket)
        else:
            bucket_cell = hint(bucket)
        score = r["pii_score"]
        score_cell = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
        table.add_row(
            str(r["name"]),
            score_cell,
            bucket_cell,
            "yes" if r["quasi_identifier"] else "",
        )
    state.console.print(table)

    if rows and scan != "-":
        first = rows[0]["name"]
        state.console.print(hint("Next:"), code(f"decoy scan show {scan} {first}"))


# ---------------------------------------------------------------------------
# `decoy scan show SCAN FIELD` -- per-field detail (was the storm verb)
# ---------------------------------------------------------------------------


def _show(
    scan: str = typer.Argument(
        ..., help="Path to a STORM scan JSON, or `-` for stdin."
    ),
    field: str = typer.Argument(..., help="Field name to inspect."),
    table: str | None = typer.Option(None, "--table", help=_TABLE_HELP),
    json_: bool = typer.Option(
        False, "--json", help="Emit the full field detail as JSON to stdout."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Per-field detail from a saved scan.

    The drill-down view of one field: PII score + bucket, detector hits,
    quasi-identifier membership. Read-only. Counts and labels only: the top
    values and sentinel values of a legacy scan are never printed.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        data = _read_table(scan, table)
    except _LOAD_ERRORS as exc:
        _emit_load_error(state, scan, exc, "scan show")
        raise typer.Exit(code=EXIT_USAGE) from None

    fields = data.get("fields", [])
    matched = next((f for f in fields if f.get("name") == field), None)

    if matched is None:
        names = [str(f.get("name", "")) for f in fields]
        suggestion = difflib.get_close_matches(field, names, n=1)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "scan show",
                    "status": "error",
                    "scan": scan,
                    "field": field,
                    "error": f"Field {field!r} not in scan.",
                    "suggestion": suggestion[0] if suggestion else None,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(
                error("error:"), f"Field {field!r} not in scan."
            )
            if suggestion:
                state.err_console.print(
                    " ", hint("hint:"), "did you mean", code(suggestion[0]),
                )
            else:
                state.err_console.print(
                    " ", hint("hint:"), "list all fields with",
                    code(f"decoy scan fields {scan}"),
                )
        raise typer.Exit(code=EXIT_USAGE)

    qi_groups = data.get("quasi_identifier_groups", [])
    qi_member = [g for g in qi_groups if field in g]
    score = matched.get("pii_score")
    bucket = _pii_bucket(score)
    detectors = matched.get("detector_hits") or []

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "scan show",
                "status": "ok",
                "scan": scan,
                "field": matched,
                "pii_bucket": bucket,
                "quasi_identifier_groups": qi_member,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    facts: list[tuple[str, str]] = [("Field", field)]
    if isinstance(score, (int, float)):
        facts.append(("PII score", f"{score:.2f} ({bucket})"))
    else:
        facts.append(("PII score", f"- ({bucket})"))
    for key, label in (
        ("dtype", "Type"),
        ("null_count", "Nulls"),
        ("distinct_count", "Distinct"),
    ):
        if key in matched and matched[key] is not None:
            facts.append((label, str(matched[key])))
    if detectors:
        facts.append(("Detectors", ", ".join(str(d) for d in detectors)))
    if qi_member:
        qi_str = ", ".join("(" + " + ".join(g) + ")" for g in qi_member)
        facts.append(("Quasi-identifier in", qi_str))

    next_hint = None
    if scan != "-":
        next_hint = f"decoy scan fields {scan}"

    render_card(
        state,
        command="decoy scan show",
        facts=facts,
        next_hint=next_hint,
        status="ok",
    )


# ---------------------------------------------------------------------------
# `decoy scan diff OLD NEW` -- compare two saved scans (was the storm verb)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanDiff:
    """The categorized difference between two saved STORM scans (pure, no I/O)."""

    added_rows: list[dict]
    removed_rows: list[dict]
    pii_increased: list[dict]
    pii_decreased: list[dict]
    qi_added: list[tuple[str, ...]]
    qi_removed: list[tuple[str, ...]]
    risk_delta: float | None
    new_high_pii: list[dict]

    @property
    def drift(self) -> bool:
        return bool(self.pii_increased or self.new_high_pii or self.qi_added)


def compute_scan_diff(old_data: dict, new_data: dict) -> ScanDiff:
    """Categorize drift between two scan dicts. Shared by `scan diff` and `decoy ci check`."""
    old_fields = {
        f.get("name"): f for f in old_data.get("fields", []) if f.get("name")
    }
    new_fields = {
        f.get("name"): f for f in new_data.get("fields", []) if f.get("name")
    }

    added_names = sorted(set(new_fields) - set(old_fields))
    removed_names = sorted(set(old_fields) - set(new_fields))
    common_names = sorted(set(old_fields) & set(new_fields))

    pii_increased: list[dict] = []
    pii_decreased: list[dict] = []
    for name in common_names:
        old_score = old_fields[name].get("pii_score") or 0
        new_score = new_fields[name].get("pii_score") or 0
        old_bucket = _pii_bucket(old_score)
        new_bucket = _pii_bucket(new_score)
        if _bucket_rank(new_bucket) > _bucket_rank(old_bucket):
            pii_increased.append(
                {
                    "name": name,
                    "old_score": old_score, "new_score": new_score,
                    "old_bucket": old_bucket, "new_bucket": new_bucket,
                }
            )
        elif _bucket_rank(new_bucket) < _bucket_rank(old_bucket):
            pii_decreased.append(
                {
                    "name": name,
                    "old_score": old_score, "new_score": new_score,
                    "old_bucket": old_bucket, "new_bucket": new_bucket,
                }
            )

    old_qi = {_canon_qi(g) for g in old_data.get("quasi_identifier_groups", [])}
    new_qi = {_canon_qi(g) for g in new_data.get("quasi_identifier_groups", [])}
    qi_added = sorted(new_qi - old_qi)
    qi_removed = sorted(old_qi - new_qi)

    old_risk = old_data.get("reid_risk_score")
    new_risk = new_data.get("reid_risk_score")
    risk_delta: float | None = None
    if isinstance(old_risk, (int, float)) and isinstance(new_risk, (int, float)):
        risk_delta = float(new_risk) - float(old_risk)

    added_rows = [
        {
            "name": n,
            "pii_score": new_fields[n].get("pii_score"),
            "pii_bucket": _pii_bucket(new_fields[n].get("pii_score")),
        }
        for n in added_names
    ]
    removed_rows = [
        {
            "name": n,
            "pii_score": old_fields[n].get("pii_score"),
            "pii_bucket": _pii_bucket(old_fields[n].get("pii_score")),
        }
        for n in removed_names
    ]

    new_high_pii = [r for r in added_rows if r["pii_bucket"] == "high"]
    return ScanDiff(
        added_rows=added_rows,
        removed_rows=removed_rows,
        pii_increased=pii_increased,
        pii_decreased=pii_decreased,
        qi_added=qi_added,
        qi_removed=qi_removed,
        risk_delta=risk_delta,
        new_high_pii=new_high_pii,
    )


def _diff(
    old: str = typer.Argument(
        ..., help="Path to the older STORM scan JSON, or `-` for stdin."
    ),
    new: str = typer.Argument(
        ..., help="Path to the newer STORM scan JSON, or `-` for stdin."
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit 1 on drift -- any PII bucket bumped up, any new high-PII field, or any new quasi-identifier group.",
    ),
    table: str | None = typer.Option(None, "--table", help=_TABLE_HELP),
    json_: bool = typer.Option(
        False, "--json", help="Emit the categorized diff as JSON to stdout."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Compare two scans -- catch schema, PII, and risk drift.

    Designed for CI: run `decoy scan diff baseline.json new.json --strict`
    on every PR to fail the build when a column's PII bucket goes up, a new
    high-PII field appears, or a new quasi-identifier group forms. Read-only
    -- the scans are JSON; raw data never enters the CLI.
    """
    state = setup_output(json_, quiet, verbose)

    if old == "-" and new == "-":
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "scan diff",
                    "status": "error",
                    "error": "only one of OLD or NEW can be `-` (stdin).",
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(
                error("error:"), "only one of OLD or NEW can be `-` (stdin)."
            )
            state.err_console.print(
                " ", hint("hint:"), "pipe one scan, pass the other as a path."
            )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        old_data = _read_table(old, table)
    except _LOAD_ERRORS as exc:
        _emit_load_error(state, old, exc, "scan diff")
        raise typer.Exit(code=EXIT_USAGE) from None
    try:
        new_data = _read_table(new, table)
    except _LOAD_ERRORS as exc:
        _emit_load_error(state, new, exc, "scan diff")
        raise typer.Exit(code=EXIT_USAGE) from None

    diff = compute_scan_diff(old_data, new_data)
    added_rows, removed_rows = diff.added_rows, diff.removed_rows
    pii_increased, pii_decreased = diff.pii_increased, diff.pii_decreased
    qi_added, qi_removed = diff.qi_added, diff.qi_removed
    risk_delta, new_high_pii, drift = diff.risk_delta, diff.new_high_pii, diff.drift

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "scan diff",
                "status": "ok",
                "old": old,
                "new": new,
                "summary": {
                    "added": len(added_rows),
                    "removed": len(removed_rows),
                    "pii_increased": len(pii_increased),
                    "pii_decreased": len(pii_decreased),
                    "qi_groups_added": len(qi_added),
                    "qi_groups_removed": len(qi_removed),
                    "reid_risk_delta": risk_delta,
                },
                "changes": {
                    "added": added_rows,
                    "removed": removed_rows,
                    "pii_increased": pii_increased,
                    "pii_decreased": pii_decreased,
                    "qi_groups_added": [list(g) for g in qi_added],
                    "qi_groups_removed": [list(g) for g in qi_removed],
                },
                "drift": drift,
            },
        )
        if strict and drift:
            raise typer.Exit(code=EXIT_USAGE)
        return

    if state.mode is OutputMode.quiet:
        if strict and drift:
            raise typer.Exit(code=EXIT_USAGE)
        return

    facts: list[tuple[str, str]] = [
        ("Old", old if old != "-" else "stdin"),
        ("New", new if new != "-" else "stdin"),
        ("Fields added", str(len(added_rows))),
        ("Fields removed", str(len(removed_rows))),
        ("PII bucket increased", str(len(pii_increased))),
        ("PII bucket decreased", str(len(pii_decreased))),
    ]
    if risk_delta is not None:
        sign = "+" if risk_delta > 0 else ""
        facts.append(("Reid risk delta", f"{sign}{risk_delta:.2f} points"))
    if qi_added or qi_removed:
        facts.append(("QI groups", f"+{len(qi_added)} -{len(qi_removed)}"))

    status_token = "warn" if drift else "ok"
    next_hint = None
    if pii_increased and new != "-":
        next_hint = f"decoy scan show {new} {pii_increased[0]['name']}"
    elif new_high_pii and new != "-":
        next_hint = f"decoy scan show {new} {new_high_pii[0]['name']}"

    render_card(
        state,
        command="decoy scan diff",
        facts=facts,
        next_hint=next_hint,
        status=status_token,
    )

    if pii_increased:
        t = make_table("Field", "Old", "New", title="PII bucket increased")
        for r in pii_increased:
            new_cell_text = f"{r['new_bucket']} ({r['new_score']:.2f})"
            if r["new_bucket"] == "high":
                new_cell = risk_high(new_cell_text)
            elif r["new_bucket"] == "med":
                new_cell = risk_med(new_cell_text)
            else:
                new_cell = new_cell_text
            t.add_row(
                r["name"],
                f"{r['old_bucket']} ({r['old_score']:.2f})",
                new_cell,
            )
        state.console.print(t)

    if pii_decreased:
        t = make_table("Field", "Old", "New", title="PII bucket decreased")
        for r in pii_decreased:
            t.add_row(
                r["name"],
                f"{r['old_bucket']} ({r['old_score']:.2f})",
                f"{r['new_bucket']} ({r['new_score']:.2f})",
            )
        state.console.print(t)

    if added_rows:
        t = make_table("Field", "PII score", "Bucket", title="Fields added")
        for r in added_rows:
            score = r["pii_score"]
            score_cell = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
            bucket = r["pii_bucket"]
            if bucket == "high":
                bucket_cell = risk_high(bucket)
            elif bucket == "med":
                bucket_cell = risk_med(bucket)
            else:
                bucket_cell = hint(bucket)
            t.add_row(r["name"], score_cell, bucket_cell)
        state.console.print(t)

    if removed_rows:
        t = make_table(
            "Field", "PII score (was)", "Bucket (was)", title="Fields removed"
        )
        for r in removed_rows:
            score = r["pii_score"]
            score_cell = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
            t.add_row(r["name"], score_cell, r["pii_bucket"])
        state.console.print(t)

    if qi_added:
        t = make_table("Group", title="Quasi-identifier groups added")
        for g in qi_added:
            t.add_row("(" + " + ".join(g) + ")")
        state.console.print(t)

    if qi_removed:
        t = make_table("Group", title="Quasi-identifier groups removed")
        for g in qi_removed:
            t.add_row("(" + " + ".join(g) + ")")
        state.console.print(t)

    if not drift and not (pii_decreased or removed_rows or qi_removed or added_rows):
        state.console.print(success("No drift detected."))

    if strict and drift:
        raise typer.Exit(code=EXIT_USAGE)


# The hidden default command: `decoy scan SOURCE` (no subcommand) routes here
# via the shared default-command group. Hidden so it stays out of help / the
# generated reference / completion, while the group can still dispatch to it.
scan_app.command(name="_scan", hidden=True, epilog=_SCAN_EPILOG)(_scan)
scan_app.command(name="fields", epilog=_FIELDS_EPILOG)(_fields)
scan_app.command(name="show", epilog=_SHOW_EPILOG)(_show)
scan_app.command(name="diff", epilog=_DIFF_EPILOG)(_diff)

SCAN_EPILOG = _SCAN_EPILOG

__all__ = ["SCAN_EPILOG", "scan_app"]
