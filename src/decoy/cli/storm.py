"""`decoy storm` -- dataset analysis (PII detectors, sentinels, re-id risk)."""

from __future__ import annotations

import difflib
import json as _json
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.storm_animation import stormy_multistage
from decoy.ui.table import make_table
from decoy.ui.theme import code, error, hint, risk_high, risk_med, success


storm_app = typer.Typer(
    name="storm",
    help="Dataset analysis -- the STORM event. Scan first, then forecast.",
    no_args_is_help=True,
)


class SampleStrategy(str, Enum):
    full = "full"
    head = "head"
    random = "random"


class PiiLevel(str, Enum):
    high = "high"
    med = "med"
    low = "low"
    none = "none"


_BUCKET_RANK: dict[str, int] = {"none": 0, "low": 1, "med": 2, "high": 3}

# Suffixes that almost certainly mean "this is raw data, not a saved scan."
# Used by `_emit_load_error` to swap the generic JSON parse hint for a
# specific "scan it first" suggestion.
_RAW_DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".parquet", ".json.gz", ".jsonl"}


_SCAN_EPILOG = """\
Examples:

  decoy storm scan data.csv
    Scan a CSV with default sampling, save scan_<timestamp>.json.

  decoy storm scan data.csv --rows 50000 --strategy random
    Sample 50K random rows.

  decoy storm scan data.csv --json > scan.json
    Pipe the full StormProfile JSON for forecast --stdin.

See also: decoy storm fields, decoy storm show, decoy forecast recommend.
"""


_FIELDS_EPILOG = """\
Examples:

  decoy storm fields scan.json
    List every field with PII score, bucket, quasi-identifier flag.

  decoy storm fields scan.json --pii high --quasi
    Only fields that are high PII *and* part of a quasi-identifier group.

  decoy storm fields scan.json --json | jq '.fields[].name'
    Pipe just the matching field names somewhere else.

See also: decoy storm show, decoy forecast recommend.
"""


_SHOW_EPILOG = """\
Examples:

  decoy storm show scan.json ssn
    Per-field detail card -- PII score, detectors, sentinels, top values, QI.

  decoy storm show scan.json email --json
    Same data as a structured JSON envelope.

  decoy storm scan data.csv --json | decoy storm show - ssn
    Pipe a fresh scan straight in.

See also: decoy storm fields, decoy forecast recommend.
"""


_DIFF_EPILOG = """\
Examples:

  decoy storm diff baseline.json new.json
    Print field-, PII-, QI-, and risk-level differences between two scans.

  decoy storm diff baseline.json new.json --strict
    Same, but exit 1 on drift (PII bucket bumped up, new high-PII field, or
    new quasi-identifier group). Wire this into CI.

  decoy storm diff baseline.json new.json --json | jq '.drift'
    Boolean drift flag for scripting.

See also: decoy storm scan, decoy storm fields.
"""


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


def _load_scan_dict(scan_path: str) -> dict:
    """Load a STORM scan JSON file (or stdin when path is `-`).

    Accepts both shapes that `decoy storm scan` produces -- the bare
    `to_dict()` written to disk by default, and the `{"profile": {...}}`
    envelope from `--json` mode. Mirrors the loader in `decoy.cli.forecast`.
    """
    if scan_path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(scan_path).read_text(encoding="utf-8")
    data = _json.loads(raw)
    if "profile" in data and "row_count" not in data:
        data = data["profile"]
    return data


def _pii_bucket(score: float | None) -> str:
    """Same buckets as the `storm scan` card uses (>=0.6 PII columns count)."""
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
    # Multi-suffix files like .json.gz where Path.suffix only sees `.gz`.
    suffixes = "".join(p.suffixes).lower()
    if any(suffixes.endswith(s) for s in _RAW_DATA_SUFFIXES):
        return True
    # Content sniff: a STORM scan JSON always starts with `{`. If the file
    # exists and the first non-whitespace char isn't `{`, it isn't a scan.
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
        scan_cmd = f"decoy storm scan {scan}"
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
                code("decoy storm scan"),
            )


def _scan(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to a CSV file to scan.",
    ),
    rows: int | None = typer.Option(
        None,
        "--rows",
        help="Sample row cap. Default: scan everything.",
    ),
    strategy: SampleStrategy = typer.Option(
        SampleStrategy.head,
        "--strategy",
        help="Sampling strategy when --rows is set.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Where to save the scan JSON. Use - for stdout. Default: scan_<timestamp>.json next to the source.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full StormProfile JSON to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Scan a dataset and produce a STORM profile.

    Use this when you've been handed a dataset and want to know what's in it
    -- which fields are PII, which look like quasi-identifiers, what
    re-identification risk the dataset carries -- before writing a masking
    pipeline. Pass the saved scan JSON to `decoy storm fields`,
    `decoy storm show`, or `decoy forecast recommend`.
    """
    state = setup_output(json_, quiet, verbose)
    source_str = str(source)

    try:
        from decoy_engine import run_storm

        with stormy_multistage(state, ["Load source", "Profile columns", "Save profile"]) as ms:
            df = _load_csv_with_sampling(source, rows, strategy)
            ms.complete()
            profile = run_storm(
                df,
                source_label=source.name,
                sample_strategy=strategy.value,
                sample_row_cap=rows,
            )
            ms.complete()

            if out is not None and str(out) == "-":
                out_path: Path | None = None
            elif out is not None:
                out_path = out
            else:
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                out_path = source.parent / f"scan_{ts}.json"

            if out_path is not None:
                out_path.write_text(_json.dumps(profile.to_dict(), indent=2))
            ms.complete()
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "storm scan",
                    "status": "error",
                    "source": source_str,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    if state.mode is OutputMode.json:
        # Full StormProfile to stdout when piping.
        if out is not None and str(out) == "-":
            sys.stdout.write(_json.dumps(profile.to_dict()) + "\n")
        else:
            emit_json(
                state,
                {
                    "command": "storm scan",
                    "status": "ok",
                    "source": source_str,
                    "saved": str(out_path) if out_path else None,
                    "profile": profile.to_dict(),
                },
            )
        return

    if state.mode is OutputMode.quiet:
        return

    pii_columns = sum(1 for f in profile.fields if f.pii_score >= 0.6)
    facts: list[tuple[str, str]] = [
        ("Source", source.name),
        ("Rows scanned", f"{profile.row_count:,} ({profile.sample_strategy})"),
        ("Columns", str(len(profile.fields))),
        ("PII columns", str(pii_columns)),
        ("Reid risk", f"{profile.reid_risk_score}"),
    ]
    if profile.quasi_identifier_groups:
        qi = ", ".join("(" + " + ".join(g) + ")" for g in profile.quasi_identifier_groups)
        facts.append(("Quasi-identifiers", qi))
    next_hint = None
    if out_path is not None:
        facts.append(("Saved", str(out_path)))
        next_hint = f"decoy storm fields {out_path}"

    render_card(
        state,
        command="decoy storm scan",
        facts=facts,
        next_hint=next_hint,
        status="ok",
    )


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
    """List fields from a saved STORM scan, with optional filters.

    The list view of the web FORECAST drill-down -- print the fields that
    matter, filter by PII bucket or quasi-identifier membership, pipe the
    result somewhere else. For per-field detail, see `decoy storm show`.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        data = _load_scan_dict(scan)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, scan, exc, "storm fields")
        raise typer.Exit(code=1)

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
                "command": "storm fields",
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
        state.console.print(hint("Next:"), code(f"decoy storm show {scan} {first}"))


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
    """Per-field detail from a saved STORM scan.

    The drill-down view of one field: PII score + bucket, detector matches,
    sentinel hits, top values, quasi-identifier membership. Stays read-only
    -- for live exploration use the web FORECAST panel.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        data = _load_scan_dict(scan)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, scan, exc, "storm show")
        raise typer.Exit(code=1)

    fields = data.get("fields", [])
    matched = next((f for f in fields if f.get("name") == field), None)

    if matched is None:
        names = [str(f.get("name", "")) for f in fields]
        suggestion = difflib.get_close_matches(field, names, n=1)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "storm show",
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
                    code(f"decoy storm fields {scan}"),
                )
        raise typer.Exit(code=1)

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
                "command": "storm show",
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
        next_hint = f"decoy forecast recommend {scan}"

    render_card(
        state,
        command="decoy storm show",
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
    """Compare two STORM scans -- catch schema, PII, and risk drift.

    Designed for CI: run `decoy storm diff baseline.json new.json --strict`
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
                    "command": "storm diff",
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
        raise typer.Exit(code=1)

    try:
        old_data = _load_scan_dict(old)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, old, exc, "storm diff")
        raise typer.Exit(code=1)
    try:
        new_data = _load_scan_dict(new)
    except (FileNotFoundError, _json.JSONDecodeError, OSError) as exc:
        _emit_load_error(state, new, exc, "storm diff")
        raise typer.Exit(code=1)

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
                "command": "storm diff",
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
            raise typer.Exit(code=1)
        return

    if state.mode is OutputMode.quiet:
        if strict and drift:
            raise typer.Exit(code=1)
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
        next_hint = f"decoy storm show {new} {pii_increased[0]['name']}"
    elif new_high_pii and new != "-":
        next_hint = f"decoy storm show {new} {new_high_pii[0]['name']}"

    render_card(
        state,
        command="decoy storm diff",
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
        raise typer.Exit(code=1)


storm_app.command(name="scan", epilog=_SCAN_EPILOG)(_scan)
storm_app.command(name="fields", epilog=_FIELDS_EPILOG)(_fields)
storm_app.command(name="show", epilog=_SHOW_EPILOG)(_show)
storm_app.command(name="diff", epilog=_DIFF_EPILOG)(_diff)
