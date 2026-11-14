"""`decoy scan SOURCES...`: resolve the files, scan them through the engine, report.

`scan.py` declares the options and calls `run_scan`; everything between the arguments and the
terminal lives here so `scan.py` does not grow.

Every positional file becomes an explicit source descriptor (a CSV states `has_header`, a
headerless one supplies its column names) and goes to the engine's `scan_sources`. Nothing is
inferred about a header. What reaches the terminal, `--json` and `--output` is built from
`scan_set_to_dict(detail=False)`, the value-free `ScanSetCore`, plus counts from the in-memory
scan. The richer per-table detail, which can hold cell values, is never requested here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import typer

from decoy._atomic import AtomicWriteError, WriteMode, describe, write_local_target
from decoy.cli._sources import csv_file_source
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.card import render_card
from decoy.ui.output import (
    OutputMode,
    OutputState,
    emit_json,
    emit_json_document,
    print_traceback,
)
from decoy.ui.storm_animation import stormy_multistage
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, warn

PII_NOTE = (
    "PII candidates are SUGGESTIONS based on STORM pattern matching. "
    "They are not authoritative classifications. Review each flagged field "
    "and decide what masking to apply. Decoy never auto-classifies PII."
)

_FIXED_WIDTH_EXTENSIONS = frozenset({".fwf", ".dat", ".fixed", ".fw"})
_PARQUET_EXTENSIONS = frozenset({".parquet", ".pq"})
_FORMAT_FLAG = {"delimited": "csv", "parquet": "parquet", "fixed-width": "fixed_width"}

# Fixed text per warning identity. The engine warnings name a table, never a cell.
_WARNING_TEXT = {
    "scan_header_suspect": (
        "the first row looks like data, not column names; check --has-header / --no-header"
    ),
    "scan_key_type_mismatch": "the declared key columns differ in type",
}


class ScanUsageError(Exception):
    """A bad invocation, found before any file is read. The message is fixed text plus names."""

    def __init__(self, message: str, hint_text: str | None = None) -> None:
        super().__init__(message)
        self.hint_text = hint_text


def table_name_from_path(path: Path) -> str:
    """The table name a positional file gets: `[a-z0-9_]`, a `t_` prefix before a digit.

    One rule for one input (positional paths). The engine walk helper keeps connector labels
    verbatim and is a different rule for a different input.
    """
    name = re.sub(r"[^a-z0-9_]", "_", path.stem.lower())
    if not name or name[0].isdigit():
        name = "t_" + name
    return name


def safe_field_record(field: Mapping[str, Any]) -> dict[str, Any]:
    """The one renderer of a field for the card, `--show-fields` and `--json` (H5).

    Takes a `FieldCore` dict and keeps counts, rates, the type label and detector ids. The core
    has no member that can hold a cell value, so none can be copied through here.
    """
    return {
        "name": field["name"],
        "dtype": field["dtype"],
        "null_rate": field["null_rate"],
        "distinct_count": field["distinct_count"],
        "pii_score": field["pii_score"],
        "pii_candidate": field["pii_candidate"],
        "detector_hits": list(field["detector_hits"]),
    }


# ---------------------------------------------------------------------------
# Argument resolution (no file is read here)
# ---------------------------------------------------------------------------


def _kind(path: Path, fmt: str | None) -> str:
    if fmt is not None:
        return _FORMAT_FLAG[fmt]
    suffix = path.suffix.lower()
    if suffix in _PARQUET_EXTENSIONS:
        return "parquet"
    if suffix in _FIXED_WIDTH_EXTENSIONS:
        return "fixed_width"
    return "csv"


def _split_names(raw: str) -> list[str]:
    names = [n.strip() for n in raw.split(",")]
    if any(not n for n in names):
        raise ScanUsageError("--column-names must be a comma-separated list of non-empty names.")
    if len(set(names)) != len(names):
        raise ScanUsageError("--column-names must not repeat a name.")
    return names


def _check_header_flags(
    paths: Sequence[Path],
    kinds: Sequence[str],
    has_header: bool | None,
    names: list[str] | None,
) -> None:
    csv_files = [p for p, k in zip(paths, kinds, strict=True) if k == "csv"]
    if names is not None:
        if has_header is not False:
            raise ScanUsageError("--column-names requires --no-header.")
        if len(paths) != 1 or len(csv_files) != 1:
            raise ScanUsageError("--column-names applies to exactly one CSV file.")
    if csv_files and has_header is None:
        raise ScanUsageError(
            f"{csv_files[0]}: say whether the first row is a header.",
            "pass --has-header (row 1 holds the column names) or --no-header "
            "(row 1 is data; give the names with --column-names a,b,c).",
        )
    if csv_files and has_header is False and names is None:
        raise ScanUsageError(
            "--no-header needs --column-names a,b,c (one name per column).",
            "a headerless file has no column names to read.",
        )


def resolve_sources(
    paths: Sequence[Path],
    *,
    fmt: str | None,
    layout: Path | None,
    has_header: bool | None,
    column_names: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Positional files to `(name -> source descriptor, name -> path as given)`, in order."""
    if len(paths) > 1 and (fmt is not None or layout is not None):
        raise ScanUsageError("--format and --layout apply to exactly one file.")
    shown: dict[str, str] = {}
    for p in paths:
        name = table_name_from_path(p)
        if name in shown:
            raise ScanUsageError(
                f"{shown[name]} and {p} both become the table {name!r}.",
                "rename one file, or scan them in separate runs.",
            )
        shown[name] = str(p)
    kinds = [_kind(p, fmt) for p in paths]
    names = _split_names(column_names) if column_names is not None else None
    _check_header_flags(paths, kinds, has_header, names)
    layout_columns = _layout_columns(layout) if "fixed_width" in kinds else None
    sources: dict[str, dict[str, Any]] = {}
    for name, p, kind in zip(shown, paths, kinds, strict=True):
        absolute = p.resolve()
        if kind == "parquet":
            sources[name] = {"type": "file", "format": "parquet", "path": str(absolute)}
        elif kind == "fixed_width":
            sources[name] = {
                "type": "file",
                "format": "fixed_width",
                "path": str(absolute),
                "layout": {"columns": layout_columns},
            }
        else:
            dialect: dict[str, Any] = {"has_header": bool(has_header)}
            if names is not None:
                dialect["column_names"] = names
            if p.suffix.lower() == ".tsv":
                dialect["delimiter"] = "\t"
            sources[name] = csv_file_source(absolute, **dialect)
    return sources, shown


def _layout_columns(layout: Path | None) -> list[dict]:
    if layout is None:
        raise ScanUsageError(
            "Fixed-width input requires --layout: column boundaries are ambiguous "
            "without an explicit layout spec.",
            "provide a layout file: decoy scan FILE --layout layout.yaml",
        )
    if not layout.exists():
        raise ScanUsageError(f"Layout file not found: {layout}")
    from decoy.cli.scan import _parse_layout

    columns: list[dict] | None = None
    try:
        columns = _parse_layout(layout)
    except Exception:
        columns = None
    # Raised outside the handler with fixed text: the parser's message quotes the rejected
    # layout literal, and the error must not chain to it.
    if columns is None:
        raise ScanUsageError(
            f"Could not parse layout file {layout.name}: it must be a mapping with a "
            "'columns' list, each column with a string 'name' and integer 'start' and 'width'."
        )
    return columns


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _emit_error(
    state: OutputState, where: dict[str, Any], message: str, hint_text: str | None
) -> None:
    if state.mode is OutputMode.json:
        emit_json(state, {"command": "scan", "status": "error", **where, "error": message})
        return
    state.err_console.print(error("error:"), message)
    if hint_text and state.mode is not OutputMode.quiet:
        state.err_console.print(" ", hint("hint:"), hint_text)


def _failure_message(exc: Exception) -> str:
    """The class (and the table, when the engine names one), never the exception text."""
    from decoy_engine.profiling import ScanSourceError

    if isinstance(exc, AtomicWriteError):
        return f"scan failed: {describe(exc)}"
    if isinstance(exc, ScanSourceError):
        return f"scan failed: table {exc.table!r}: {exc.cause_class}"
    return f"scan failed: {type(exc).__name__}"


def _warning_lines(table: Mapping[str, Any]) -> list[str]:
    return [
        f"table {table['name']!r}: {_WARNING_TEXT.get(w['code'], 'warning ' + w['code'])}."
        for w in table["warnings"]
    ]


def _table_summary(core_table: Mapping[str, Any], scan: Any, shown_path: str, show: bool) -> dict:
    """Per-table facts: counts and names from the core, scanned rows from the profile."""
    fields = [safe_field_record(f) for f in core_table["fields"]]
    summary: dict[str, Any] = {
        "name": core_table["name"],
        "source": shown_path,
        "row_count": scan.profile.row_count,
        "field_count": len(fields),
        "sample_strategy": scan.profile.sample_strategy,
        "pii_candidate_count": sum(1 for f in fields if f["pii_candidate"]),
        "reid_risk_score": scan.profile.reid_risk_score,
        "k_anonymity": scan.profile.k_anonymity,
        "quasi_identifier_groups": core_table["quasi_identifier_groups"],
        "key_candidates": core_table["key_candidates"],
        "warnings": list(core_table["warnings"]),
    }
    if show:
        summary["fields"] = fields
    return summary


def _flat_payload(t: Mapping[str, Any], saved: str | None, show: bool) -> dict[str, Any]:
    """The long-standing single-file `--json` keys, unchanged."""
    payload: dict[str, Any] = {
        "command": "scan",
        "status": "ok",
        "source": t["source"],
        "row_count": t["row_count"],
        "field_count": t["field_count"],
        "sample_strategy": t["sample_strategy"],
        "pii_candidate_count": t["pii_candidate_count"],
        "pii_note": PII_NOTE,
        "reid_risk_score": t["reid_risk_score"],
        "quasi_identifier_groups": t["quasi_identifier_groups"],
        "saved": saved,
    }
    if show:
        payload["fields"] = t["fields"]
    if t["warnings"]:
        payload["warnings"] = t["warnings"]
    return payload


def _multi_payload(tables: list[dict], saved: str | None) -> dict[str, Any]:
    return {
        "command": "scan",
        "status": "ok",
        "scan_schema": "scan-set/v1",
        "pii_note": PII_NOTE,
        "tables": tables,
        "relationships": [],
        "saved": saved,
    }


def render_fields(state: OutputState, field_records: list[dict], pii_candidate_count: int) -> None:
    """The privacy-safe per-field table, then the honesty framing (H4)."""
    state.console.print(accent(f"Fields ({len(field_records)}):"))
    tbl = make_table("Field", "Type", "Null rate", "Distinct", "PII candidate")
    for f in field_records:
        pii_cell = ""
        if f["pii_candidate"]:
            pii_cell = "suggestion -- review"
            if f["detector_hits"]:
                pii_cell += f" [{', '.join(f['detector_hits'])}]"
        rate = f["null_rate"]
        tbl.add_row(
            f["name"],
            f["dtype"],
            "-" if rate is None else f"{rate:.1%}",
            str(f["distinct_count"]),
            pii_cell,
        )
    state.console.print(tbl)
    state.console.print()
    if pii_candidate_count > 0:
        render_pii_honesty(state, pii_candidate_count)


def render_pii_honesty(state: OutputState, pii_candidate_count: int) -> None:
    """The profile-honesty framing block (H4): candidates are suggestions."""
    state.console.print(
        warn("PII candidates:"),
        f"{pii_candidate_count} field(s) flagged by STORM pattern matching.",
    )
    state.console.print(
        " ", hint("These are SUGGESTIONS for review -- NOT authoritative classifications.")
    )
    state.console.print(
        " ",
        "Review each flagged field and choose the masking strategy that fits.",
        "Use",
        code("decoy list templates"),
        "to browse available templates.",
    )
    state.console.print()


def _score(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.1f}"


def _pii_fact(count: int) -> str:
    if count > 0:
        return f"{count} field(s) -- suggestions only, review required"
    return "none detected"


def _render_single(
    state: OutputState, t: Mapping[str, Any], saved: str | None, header_flag: str
) -> None:
    k = t["k_anonymity"]
    facts: list[tuple[str, str]] = [
        ("Source", Path(t["source"]).name),
        ("Rows scanned", f"{t['row_count']:,} ({t['sample_strategy']})"),
        ("Columns", str(t["field_count"])),
        ("PII candidates", _pii_fact(t["pii_candidate_count"])),
        ("Reid risk", f"{_score(t['reid_risk_score'])} / 100 (k={k if k is not None else 'n/a'})"),
    ]
    if t["quasi_identifier_groups"]:
        qi = ", ".join("(" + " + ".join(g) + ")" for g in t["quasi_identifier_groups"])
        facts.append(("Quasi-identifiers", qi))
    facts.append(("Key candidates", ", ".join(t["key_candidates"]) or "none"))
    if saved is not None:
        facts.append(("Saved", saved))
        next_hint = f"decoy scan fields {saved}"
    else:
        name = Path(t["source"]).name
        next_hint = (
            f"decoy scan {name}{header_flag} --output scan.json  "
            "(then: decoy scan fields scan.json)"
        )
    render_card(state, command="decoy scan", facts=facts, next_hint=next_hint, status="ok")


def _render_multi(state: OutputState, tables: list[dict], saved: str | None) -> None:
    facts = [
        ("Tables", str(len(tables))),
        ("Rows scanned", f"{sum(t['row_count'] for t in tables):,}"),
        ("PII candidates", _pii_fact(sum(t["pii_candidate_count"] for t in tables))),
    ]
    if saved is not None:
        facts.append(("Saved", saved))
        next_hint = f"decoy scan fields {saved} --table {tables[0]['name']}"
    else:
        next_hint = "add --output scan.json to save this scan"
    render_card(state, command="decoy scan", facts=facts, next_hint=next_hint, status="ok")
    tbl = make_table("Table", "Rows scanned", "Columns", "PII candidates", "Reid risk", "Keys")
    for t in tables:
        tbl.add_row(
            f"{t['name']} <- {t['source']}",
            f"{t['row_count']:,} ({t['sample_strategy']})",
            str(t["field_count"]),
            str(t["pii_candidate_count"]),
            _score(t["reid_risk_score"]),
            ", ".join(t["key_candidates"]) or "-",
        )
    state.console.print(tbl)


def run_scan(
    state: OutputState,
    *,
    sources: Sequence[Path],
    show_fields: bool,
    rows: int,
    strategy: str,
    out: Path | None,
    fmt: str | None,
    layout: Path | None,
    has_header: bool | None,
    column_names: str | None,
) -> None:
    """The body of `decoy scan SOURCES...`. Exits through `typer.Exit`."""
    given = [str(p) for p in sources]
    where: dict[str, Any] = {"source": given[0]} if len(given) == 1 else {"sources": given}
    streamed = out is not None and str(out) == "-"
    try:
        if streamed and state.mode is not OutputMode.default:
            flag = "json" if state.mode is OutputMode.json else "quiet"
            raise ScanUsageError(
                f"--output - (stream the scan to stdout) cannot be combined with --{flag}: "
                "both own stdout.",
                "save to a file (--output scan.json), or drop the conflicting flag.",
            )
        descriptors, paths = resolve_sources(
            sources, fmt=fmt, layout=layout, has_header=has_header, column_names=column_names
        )
    except ScanUsageError as exc:
        _emit_error(state, where, str(exc), exc.hint_text)
        raise typer.Exit(code=EXIT_USAGE) from None

    # --rows 0 reads the whole file; otherwise --strategy picks the bounded sample.
    row_cap: int | None = None if rows == 0 else rows
    effective = "full" if rows == 0 else strategy
    out_path: Path | None = out if (out is not None and not streamed) else None
    try:
        from decoy_engine import scan_set_to_dict, scan_sources

        with stormy_multistage(state, ["Load source", "Profile columns", "Summarize"]) as ms:
            result = scan_sources(
                descriptors,
                sample_rows=row_cap,
                strategy=effective,  # type: ignore[arg-type]
            )
            ms.complete()
            core = scan_set_to_dict(result, detail=False)
            ms.complete()
            # PERSIST ONLY on --output (H7b). The file is the value-free core, written once
            # after every table succeeded, so a failed table leaves no partial file.
            if out_path is not None:
                write_local_target(
                    out_path, json.dumps(core, indent=2).encode("utf-8"), WriteMode.REPLACE
                )
            ms.complete()
    except Exception as exc:
        # Never str(exc): engine parse errors can embed raw cell data.
        _emit_error(state, where, _failure_message(exc), "rerun with --verbose for the traceback.")
        if state.verbose:
            state.err_console.print(
                hint("(--verbose: traceback below; diagnostic output may contain row data)")
            )
            print_traceback(state)
        raise typer.Exit(code=EXIT_RUNTIME) from None

    if streamed:
        emit_json_document(state, core, indent=None)
        return

    saved = str(out_path) if out_path else None
    tables = [
        _table_summary(ct, st, paths[ct["name"]], show_fields)
        for ct, st in zip(core["tables"], result.tables, strict=True)
    ]
    single = len(tables) == 1
    if state.mode is OutputMode.json:
        emit_json(
            state,
            _flat_payload(tables[0], saved, show_fields)
            if single
            else _multi_payload(tables, saved),
        )
        return
    if state.mode is OutputMode.quiet:
        return
    for t in tables:
        for line in _warning_lines(t):
            state.err_console.print(warn("warning:"), line)

    if single:
        header_flag = (
            "" if has_header is None else (" --has-header" if has_header else " --no-header")
        )
        _render_single(state, tables[0], saved, header_flag)
    else:
        _render_multi(state, tables, saved)
    total_pii = sum(t["pii_candidate_count"] for t in tables)
    if show_fields:
        for t in tables:
            state.console.print()
            if not single:
                state.console.print(accent(f"Table {t['name']}"))
            render_fields(state, t["fields"], t["pii_candidate_count"])
    elif total_pii > 0:
        state.console.print()
        render_pii_honesty(state, total_pii)
        state.console.print(hint("Tip:"), "add", code("--show-fields"), "for per-field detail.")
