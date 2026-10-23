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
  privacy-safe `_safe_field_record` -- dtype, null_rate, distinct_count,
  pii_score, detector ids ONLY. It NEVER includes top_values, mode/min/max, or
  any aggregate that could expose raw cell data. (The `--output` artifact keeps
  the engine's richer `profile.to_dict()`; that is pre-existing and intentional.)

Reuses the engine's `run_storm` function. Does NOT reimplement detection.
"""

from __future__ import annotations

import difflib
import json as _json
import sys
from enum import Enum
from pathlib import Path

import typer

from decoy.cli._default_group import make_default_group
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.storm_animation import stormy_multistage
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, risk_high, risk_med, success, warn

_SCAN_GROUP_HELP = (
    "Profile a dataset for PII and re-identification risk. `decoy scan "
    "SOURCE` scans a CSV/Parquet/fixed-width file (shape, field stats, PII "
    "candidates as suggestions, quasi-identifiers, reid risk) and, with "
    "`--output scan.json`, saves the scan. Subcommands operate on a saved "
    "scan: list fields (`fields`), per-field detail (`show`), compare two "
    "scans (`diff`)."
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

  decoy scan data.csv
    Profile a CSV: row/field counts, PII candidates (as suggestions), reid risk.
    Reads the first 10 000 rows by default (--rows 0 for a full scan).

  decoy scan data.csv --show-fields
    Per-field detail: dtype, null_rate, distinct_count, PII candidate flag.

  decoy scan data.csv --rows 50000 --strategy random
    Sample 50K random rows instead of the first 10 000.

  decoy scan data.csv --output scan.json
    Save the scan to scan.json, then: decoy scan fields scan.json

  decoy scan data.csv --output -
    Stream the scan JSON to stdout for downstream tooling.

  decoy scan records.fwf --layout layout.yaml
    Scan a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

HONESTY: PII candidates are SUGGESTIONS based on STORM pattern matching. They
are NOT authoritative classifications. You review each flagged field and decide
what masking to apply. Decoy never auto-classifies PII.

No raw cell values appear in the inline output. Field stats include dtype,
null_rate, distinct_count only.

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
    Per-field detail card -- PII score, detectors, sentinels, top values, QI.

  decoy scan show scan.json email --json
    Same data as a structured JSON envelope.

  decoy scan data.csv --output - | decoy scan show - ssn
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


def _load_scan_dict(scan_path: str) -> dict:
    """Load a STORM scan JSON file (or stdin when path is `-`).

    Accepts both shapes `decoy scan` produces -- the bare `to_dict()` written
    to disk by `--output FILE`, and the `{"profile": {...}}` envelope some
    tools wrap it in.
    """
    try:
        if scan_path == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(scan_path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError is a ValueError, not an OSError, so the callers
        # that catch (FileNotFoundError, JSONDecodeError, OSError) would let a
        # non-UTF-8 scan file crash with a raw traceback and corrupt --json
        # output. Normalise to OSError so the existing handlers emit a clean
        # error. (QA 2026-06-04 storm-validate-cli F1.)
        raise OSError(f"scan file is not valid UTF-8: {exc}") from exc
    data = _json.loads(raw)
    if "profile" in data and "row_count" not in data:
        data = data["profile"]
    return data


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
        scan_cmd = f"decoy scan {scan} --output scan.json"
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


# ---------------------------------------------------------------------------
# Privacy-safe field record (H5). Carried from `profile`.
# ---------------------------------------------------------------------------


def _safe_field_record(field_stats) -> dict:
    """Return a privacy-safe field record from a FieldStats object.

    Includes ONLY: name, inferred_type (dtype), null_rate, distinct_count,
    pii_score, pii_candidate (bool), detector ids (names only, no match
    details).

    NEVER includes: top_values, mode_value, min_value, max_value, sample_invalid,
    mean_value, or any other aggregate that could expose raw cell data.
    """
    is_candidate = field_stats.pii_score >= _PII_CANDIDATE_THRESHOLD
    # Detector IDs only (no match rates, no sample_misses which could be raw data).
    detector_ids = [m.detector_id for m in (field_stats.detector_matches or [])]
    return {
        "name": field_stats.name,
        "dtype": field_stats.inferred_type,
        "null_rate": round(field_stats.null_rate, 4),
        "distinct_count": field_stats.distinct_count,
        "pii_score": round(field_stats.pii_score, 3),
        "pii_candidate": is_candidate,
        # Detector IDs are safe metadata (pattern names, not cell values).
        "detector_hits": detector_ids,
    }


_PII_NOTE = (
    "PII candidates are SUGGESTIONS based on STORM pattern matching. "
    "They are not authoritative classifications. Review each flagged field "
    "and decide what masking to apply. Decoy never auto-classifies PII."
)


def _render_fields(state, field_records: list[dict], pii_candidate_count: int) -> None:
    """Render the privacy-safe per-field detail table + honesty framing."""
    state.console.print(accent(f"Fields ({len(field_records)}):"))

    tbl = make_table("Field", "Type", "Null rate", "Distinct", "PII candidate")
    for f in field_records:
        pii_cell = ""
        if f["pii_candidate"]:
            detectors = ", ".join(f["detector_hits"]) if f["detector_hits"] else ""
            pii_cell = "suggestion -- review"
            if detectors:
                pii_cell += f" [{detectors}]"
        tbl.add_row(
            f["name"],
            f["dtype"],
            f"{f['null_rate']:.1%}",
            str(f["distinct_count"]),
            pii_cell,
        )
    state.console.print(tbl)
    state.console.print()

    if pii_candidate_count > 0:
        _render_pii_honesty(state, pii_candidate_count)


def _render_pii_honesty(state, pii_candidate_count: int) -> None:
    """The profile-honesty framing block (H4): candidates are suggestions."""
    state.console.print(
        warn("PII candidates:"),
        f"{pii_candidate_count} field(s) flagged by STORM pattern matching.",
    )
    state.console.print(
        " ",
        hint("These are SUGGESTIONS for review -- NOT authoritative classifications."),
    )
    state.console.print(
        " ",
        "Review each flagged field and choose the masking strategy that fits.",
        "Use",
        code("decoy list templates"),
        "to browse available templates.",
    )
    state.console.print()


# ---------------------------------------------------------------------------
# `decoy scan SOURCE` -- the default command (merges profile + storm analyze)
# ---------------------------------------------------------------------------


def _scan(
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
            "Save the scan JSON to this path. Use - for stdout. "
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
        help="Emit a structured JSON result on stdout instead of the styled card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Profile a source dataset: shape, field stats, PII candidates, reid risk.

    Runs STORM detection on the source file. PII candidates are surfaced as
    SUGGESTIONS for review -- never as authoritative auto-classifications.
    No raw cell values appear in the inline output. Save the scan with
    `--output scan.json`, then operate on it with `decoy scan fields/show/diff`.

    Supported formats: delimited (CSV/TSV, default), parquet, and fixed-width.
    Fixed-width input requires an explicit --layout spec (column boundaries are
    ambiguous without one). Format is inferred from the extension when --format
    is not supplied.
    """
    state = setup_output(json_, quiet, verbose)
    source_str = str(source)

    # Resolve the effective format (explicit flag overrides extension detection).
    effective_fmt: InputFormat = fmt if fmt is not None else _infer_format(source)

    # Fail closed early: fixed-width without a layout is always an error.
    if effective_fmt is InputFormat.fixed_width and layout is None:
        msg = (
            f"Fixed-width input requires --layout: column boundaries in {source.name} "
            "are ambiguous without an explicit layout spec. "
            "Run: decoy scan <file> --layout <layout.yaml>"
        )
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "scan", "status": "error", "source": source_str, "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("hint:"),
                "provide a layout file:",
                code(f"decoy scan {source.name} --layout layout.yaml"),
            )
        raise typer.Exit(code=EXIT_USAGE)

    # Load layout spec if needed.
    layout_columns: list[dict] | None = None
    if layout is not None:
        if not layout.exists():
            msg = f"Layout file not found: {layout}"
            if state.mode is OutputMode.json:
                emit_json(
                    state,
                    {"command": "scan", "status": "error", "source": source_str, "error": msg},
                )
            elif state.mode is not OutputMode.quiet:
                state.err_console.print(error("error:"), msg)
            raise typer.Exit(code=EXIT_USAGE)
        try:
            layout_columns = _parse_layout(layout)
        except Exception as exc:
            msg = f"Could not parse layout file {layout.name}: {exc}"
            if state.mode is OutputMode.json:
                emit_json(
                    state,
                    {"command": "scan", "status": "error", "source": source_str, "error": msg},
                )
            elif state.mode is not OutputMode.quiet:
                state.err_console.print(error("error:"), msg)
            raise typer.Exit(code=EXIT_USAGE)

    # --rows default 10000 bounds the sample (profile's safe default); --rows 0
    # scans the whole file. A bounded scan uses --strategy; a full scan ignores it.
    row_cap: int | None = None if rows == 0 else rows
    effective_strategy = SampleStrategy.full if rows == 0 else strategy

    try:
        from decoy_engine import run_storm

        with stormy_multistage(state, ["Load source", "Profile columns", "Summarize"]) as ms:
            df = _load_data(source, effective_fmt, layout_columns, row_cap, effective_strategy)
            ms.complete()
            profile = run_storm(
                df,
                source_label=source.name,
                sample_strategy=effective_strategy.value,
                sample_row_cap=row_cap,
            )
            ms.complete()

            # PERSIST ONLY on --output (H7b): no auto scan_<ts>.json to cwd.
            streamed = out is not None and str(out) == "-"
            out_path: Path | None = out if (out is not None and not streamed) else None
            if out_path is not None:
                # The on-disk artifact keeps the engine's richer profile.to_dict()
                # (pre-existing); the inline/--json field output stays privacy-safe.
                out_path.write_text(_json.dumps(profile.to_dict(), indent=2))
            ms.complete()
    except Exception as exc:
        # Do NOT interpolate str(exc) -- engine parse errors can embed raw cell
        # data in their messages. Report only the exception class name.
        msg = f"scan failed: {type(exc).__name__}"
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "scan", "status": "error", "source": source_str, "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ", hint("hint:"), "rerun with --verbose for the full traceback."
            )
        if state.verbose:
            state.err_console.print(
                hint("(--verbose: traceback below; diagnostic output may contain row data)")
            )
            state.err_console.print_exception()
        raise typer.Exit(code=EXIT_RUNTIME)

    # --output - streams the scan JSON (the richer artifact) to stdout, nothing else.
    if streamed:
        sys.stdout.write(_json.dumps(profile.to_dict()) + "\n")
        return

    # Privacy-safe field records (no raw cell values) for inline / --json output.
    field_records = [_safe_field_record(f) for f in profile.fields]
    pii_candidate_count = sum(
        1 for f in profile.fields if f.pii_score >= _PII_CANDIDATE_THRESHOLD
    )

    if state.mode is OutputMode.json:
        payload: dict = {
            "command": "scan",
            "status": "ok",
            "source": source_str,
            "row_count": profile.row_count,
            "field_count": len(profile.fields),
            "sample_strategy": profile.sample_strategy,
            "pii_candidate_count": pii_candidate_count,
            # H4: the honesty note travels in --json too.
            "pii_note": _PII_NOTE,
            "reid_risk_score": profile.reid_risk_score,
            "quasi_identifier_groups": [list(g) for g in profile.quasi_identifier_groups],
            "saved": str(out_path) if out_path else None,
        }
        if show_fields:
            payload["fields"] = field_records
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable: a run-summary card with PII framed as suggestions (H4).
    facts: list[tuple[str, str]] = [
        ("Source", source.name),
        ("Rows scanned", f"{profile.row_count:,} ({profile.sample_strategy})"),
        ("Columns", str(len(profile.fields))),
    ]
    if pii_candidate_count > 0:
        facts.append(
            ("PII candidates", f"{pii_candidate_count} field(s) -- suggestions only, review required")
        )
    else:
        facts.append(("PII candidates", "none detected"))
    facts.append(("Reid risk", f"{profile.reid_risk_score}"))
    if profile.quasi_identifier_groups:
        qi = ", ".join("(" + " + ".join(g) + ")" for g in profile.quasi_identifier_groups)
        facts.append(("Quasi-identifiers", qi))

    next_hint: str | None
    if out_path is not None:
        facts.append(("Saved", str(out_path)))
        next_hint = f"decoy scan fields {out_path}"
    else:
        # Persist-only-on-output: point at the two-step saved-scan flow.
        next_hint = f"decoy scan {source.name} --output scan.json  (then: decoy scan fields scan.json)"

    render_card(state, command="decoy scan", facts=facts, next_hint=next_hint, status="ok")

    if show_fields:
        state.console.print()
        _render_fields(state, field_records, pii_candidate_count)
    elif pii_candidate_count > 0:
        state.console.print()
        _render_pii_honesty(state, pii_candidate_count)
        state.console.print(hint("Tip:"), "add", code("--show-fields"), "for per-field detail.")


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
        data = _load_scan_dict(scan)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, scan, exc, "scan fields")
        raise typer.Exit(code=EXIT_USAGE)

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

    The drill-down view of one field: PII score + bucket, detector matches,
    sentinel hits, top values, quasi-identifier membership. Read-only.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        data = _load_scan_dict(scan)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, scan, exc, "scan show")
        raise typer.Exit(code=EXIT_USAGE)

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
    detectors = matched.get("detector_matches", []) or []
    sentinels = matched.get("sentinels", []) or []
    top_values = matched.get("top_values", []) or []

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
        ("unique_count", "Distinct"),
    ):
        if key in matched and matched[key] is not None:
            facts.append((label, str(matched[key])))
    if detectors:
        names = [
            str(d.get("detector") or d.get("name") or "?")
            if isinstance(d, dict)
            else str(d)
            for d in detectors
        ]
        facts.append(("Detectors", ", ".join(names)))
    if sentinels:
        facts.append(("Sentinels", str(len(sentinels))))
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

    if top_values:
        t = make_table("Value", "Count", title="Top values")
        for tv in top_values[:10]:
            if isinstance(tv, dict):
                v = str(tv.get("value", ""))
                c = str(tv.get("count", ""))
            else:
                v, c = str(tv), ""
            t.add_row(v, c)
        state.console.print(t)

    if sentinels:
        t = make_table("Sentinel", "Count", title="Sentinel hits")
        for s in sentinels:
            if isinstance(s, dict):
                v = str(s.get("value") or s.get("kind") or "?")
                c = str(s.get("count", ""))
            else:
                v, c = str(s), ""
            t.add_row(v, c)
        state.console.print(t)


# ---------------------------------------------------------------------------
# `decoy scan diff OLD NEW` -- compare two saved scans (was the storm verb)
# ---------------------------------------------------------------------------


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
        old_data = _load_scan_dict(old)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, old, exc, "scan diff")
        raise typer.Exit(code=EXIT_USAGE)
    try:
        new_data = _load_scan_dict(new)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, new, exc, "scan diff")
        raise typer.Exit(code=EXIT_USAGE)

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
    drift = bool(pii_increased or new_high_pii or qi_added)

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
        facts.append(("Reid risk delta", f"{sign}{risk_delta:.2f}"))
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
