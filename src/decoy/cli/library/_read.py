"""`decoy library list`, `show`, `diff` and `ref` (plan 4.3a, 4.5, 4.15; L4a).

Listing reads the index (no record file is opened); `show` and `diff` read records through
`Library.get` (the one id-checked read); `ref` reads a ref file or moves it under the library
lock. A record of a kind this version does not know is listed and shown by its envelope only
(4.3a). Output is value-free like the records: names, counts, codes, states, digests. Envelopes
print in their stored (canonical, key-sorted) order, so no second sort is needed. Errors go to
stderr with the exit code; `--json` stdout carries only a successful result.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.library._cli import fail, fail_library, library_option, open_or_fail, root_or_fail
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output

__all__ = ["diff_command", "list_command", "ref_command", "show_command"]


def _kinds(incomplete: str) -> list[str]:
    from decoy_engine.records import registered_kinds

    return [s.kind for s in registered_kinds() if s.kind.startswith(incomplete)]


def _say(state: OutputState, *parts: object) -> None:
    if state.mode is OutputMode.default:
        state.console.print(*parts, soft_wrap=True, markup=False, highlight=False)


def _instant(text: str) -> datetime:
    """A `YYYY-MM-DD` date (midnight UTC) or an ISO time; a time with no zone is UTC."""
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _row_json(row: Any) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "payload_schema": row.payload_schema,
        "created_at": row.created_at,
        "invocation_id": row.invocation_id,
        "pipeline": row.pipeline,
        "tables": list(row.tables),
        "status": row.status,
        "known": row.known,
        "links": [{"rel": rel, "id": dst} for rel, dst in row.links],
    }


def list_command(
    kind: str | None = typer.Option(
        None,
        "--kind",
        metavar="KIND",
        autocompletion=_kinds,
        help="Only records of this kind (scan-set, evidence, run-result, sample-run, ...).",
    ),
    pipeline: str | None = typer.Option(
        None, "--pipeline", metavar="P", help="Only this pipeline."
    ),
    table: str | None = typer.Option(
        None, "--table", metavar="T", help="Only records naming this table."
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        metavar="D",
        help="Only records made at or after D (YYYY-MM-DD or ISO time).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit the records as JSON, oldest first."),
    library: Path | None = library_option(),
) -> None:
    """List stored records, oldest first, from the index (no record file is opened)."""
    state = setup_output(json_, False, False)
    cutoff: datetime | None = None
    if since is not None:
        try:
            cutoff = _instant(since)
        except ValueError:
            cutoff = None
        if cutoff is None:
            fail(state, "--since takes a date (YYYY-MM-DD) or an ISO time")
    opened = open_or_fail(state, root_or_fail(state, library).path)
    rows = [
        r
        for r in opened.rows(kind=kind, pipeline=pipeline, table=table)
        if cutoff is None or _instant(r.created_at) >= cutoff
    ]
    emit_json(
        state,
        {"command": "library list", "count": len(rows), "records": [_row_json(r) for r in rows]},
    )
    if not rows:
        _say(state, "no records")
    for r in rows:
        what = r.kind if r.known else f"unknown kind {r.kind}, needs a newer Decoy"
        tables = ",".join(r.tables) or "-"
        _say(state, r.id[:19], r.created_at, what, r.pipeline or "-", tables, r.status or "-")
    raise typer.Exit(code=EXIT_OK)


def _target(state: OutputState, opened: Any, text: str) -> str:
    from decoy.cli.library._resolve import TargetError, resolve_target

    problem: str | None = None
    try:
        return resolve_target(opened, text)
    except TargetError as exc:
        problem = str(exc)
    fail(state, problem or "no record")


def _read(state: OutputState, opened: Any, record_id: str) -> Any:
    from decoy.cli.library._errors import LibraryError

    caught: LibraryError | None = None
    try:
        return opened.get(record_id)
    except LibraryError as exc:
        caught = exc
    fail_library(state, caught)  # type: ignore[arg-type]


def _status(record: Any) -> str:
    from decoy_engine import records

    if isinstance(record, records.DecodedRecord):
        return "known"
    return "opaque" if isinstance(record, records.OpaqueRecord) else "needs_newer"


def show_command(
    target: str = typer.Argument(
        ..., metavar="ID|REF", help="An id, a unique 8+ hex prefix, KIND/NAME or KIND/latest~N."
    ),
    json_: bool = typer.Option(False, "--json", help="Emit the record as JSON."),
    library: Path | None = library_option(),
) -> None:
    """Show one record: its envelope and, when this version can read it, its payload."""
    state = setup_output(json_, False, False)
    opened = open_or_fail(state, root_or_fail(state, library).path)
    record = _read(state, opened, _target(state, opened, target))
    status = _status(record)
    raw = dict(record.raw)
    shown = raw if status == "known" else {k: v for k, v in raw.items() if k != "payload"}
    emit_json(
        state,
        {
            "command": "library show",
            "status": status,
            "payload_schema": raw.get("payload_schema"),
            "record": shown,
        },
    )
    for key in ("id", "kind", "payload_schema", "created_at", "invocation_id"):
        _say(state, f"{key}:", str(raw.get(key)))
    for key in ("producer", "labels", "links"):
        _say(state, f"{key}:", json.dumps(raw.get(key)))
    if status == "known":
        _say(state, "payload:", json.dumps(raw.get("payload"), indent=2))
    elif status == "opaque":
        _say(state, "payload: cannot be read by this version (unknown kind); needs a newer Decoy")
    else:
        _say(state, "payload: written under a newer version; needs a newer Decoy")
    raise typer.Exit(code=EXIT_OK)


def diff_command(
    a: str = typer.Argument(
        ..., metavar="A", help="The older record: id, prefix, KIND/NAME or KIND/latest~N."
    ),
    b: str = typer.Argument(..., metavar="B", help="The newer record, in the same forms."),
    json_: bool = typer.Option(False, "--json", help="Emit the diff as JSON."),
    library: Path | None = library_option(),
) -> None:
    """Compare two records of the same kind (scan-set, evidence and run-result have their own rules)."""
    from decoy_engine.records import kind_spec

    from decoy.cli.library._diff import diff_payloads

    state = setup_output(json_, False, False)
    opened = open_or_fail(state, root_or_fail(state, library).path)
    ids = [_target(state, opened, text) for text in (a, b)]
    old, new = (_read(state, opened, rid) for rid in ids)
    if _status(old) != "known" or _status(new) != "known":
        fail(state, "cannot diff a record of a kind or version this Decoy cannot read")
    if old.kind != new.kind:
        fail(state, f"cannot diff records of different kinds ({old.kind} and {new.kind})")
    spec = kind_spec(old.kind)
    rule, found = diff_payloads(
        spec.diff_rule if spec else None, old.raw["payload"], new.raw["payload"]
    )
    emit_json(
        state,
        {
            "command": "library diff",
            "kind": old.kind,
            "rule": rule,
            "a": ids[0],
            "b": ids[1],
            "diff": found,
        },
    )
    _say(state, f"{old.kind} {ids[0][:19]} -> {ids[1][:19]} ({rule})")
    _say(state, json.dumps(found, indent=2))
    raise typer.Exit(code=EXIT_OK)


def ref_command(
    name: str = typer.Argument(
        ..., metavar="NAME", help="KIND/NAME or KIND/SCOPE/NAME, for example scan-set/baseline."
    ),
    record: str | None = typer.Argument(
        None, metavar="[ID]", help="Set the ref to this record (id, prefix or ref)."
    ),
    library: Path | None = library_option(),
) -> None:
    """Show a stored ref, or set it to a record (under the library lock)."""
    from decoy.cli.library._errors import LibraryError

    state = setup_output(False, False, False)
    kind, _, rest = name.partition("/")
    if not rest:
        fail(state, "a ref name is KIND/NAME, for example scan-set/baseline")
    opened = open_or_fail(state, root_or_fail(state, library).path)
    caught: LibraryError | None = None
    current: str | None = None
    try:
        if record is None:
            current = opened.read_ref(kind, rest)
        else:
            current = _target(state, opened, record)
            opened.set_ref(kind, rest, current)
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        fail_library(state, caught)
    if current is None:
        fail(state, "no ref of that name is set", EXIT_USAGE)
    _say(state, current)
    raise typer.Exit(code=EXIT_OK)
