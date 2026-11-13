"""`decoy library export`: write the library as `decoy-library-export/v1` (plan 4.11, 4.3a; L4b).

The engine owns the codec (`decoy_engine.records.export_lines` and each kind's `export_rule`) so
the platform importer reads exactly what is written: path fields reduced to file names, link
remapping, recomputed ids, the `source_id` wrapper and the header are all the engine's. The CLI
only chooses the records, hands over their raw verified envelopes (`Library.get(...).raw`, never
a typed view) in link order (every link target before the record that links to it), names the
refs, and writes the lines through the atomic writer's user-path form (0600).

Owner decision (2026-11-12): the codec's behavior is accepted. A default export withholds the
records this version cannot strip (an unknown kind, or a payload with fields this version does
not know) and names them in the header's `withheld_records`; `--keep-paths` exports every record
byte for byte. Scratch is never read. Job logs do not exist until L5b, so `--include-logs`
exports none for now.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from decoy.cli.exit_codes import EXIT_OK
from decoy.cli.library._cli import fail, fail_library, library_option, open_or_fail, root_or_fail
from decoy.ui.output import OutputMode, OutputState, setup_output
from decoy.ui.theme import warn

if TYPE_CHECKING:
    from decoy.cli.library._index import IndexRow
    from decoy.cli.library._store import Library

__all__ = ["export_command", "link_order", "select"]


def _refs_by_name(library: Library) -> dict[str, str]:
    from decoy.cli.library._paths import REFS
    from decoy.cli.library._refs import iter_refs

    refs_dir = library.library_dir / REFS
    return {
        path.relative_to(refs_dir).as_posix(): rid
        for path, rid in iter_refs(refs_dir)
        if rid is not None
    }


def _reachable(start: str, rows: dict[str, IndexRow]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        rid = stack.pop()
        if rid in seen or rid not in rows:
            continue
        seen.add(rid)
        stack.extend(dst for _rel, dst in rows[rid].links)
    return seen


def select(
    library: Library,
    *,
    kind: str | None,
    since: datetime | None,
    ref: str | None,
    target: str | None,
) -> tuple[list[str], dict[str, str]]:
    """The record ids to export and the refs to name. `target` is `ref` resolved to an id."""
    rows = {row.id: row for row in library.rows()}
    named = _refs_by_name(library)
    if target is not None:
        chosen = _reachable(target, rows)
        refs = {ref: target} if ref in named else {}
    else:
        chosen = set(rows)
        refs = {name: rid for name, rid in sorted(named.items()) if rid in chosen}
    if kind is not None:
        chosen = {rid for rid in chosen if rows[rid].kind == kind}
    if since is not None:
        from decoy.cli.library._read import _instant

        chosen = {rid for rid in chosen if _instant(rows[rid].created_at) >= since}
    return link_order([rows[rid] for rid in chosen]), refs


def link_order(rows: Sequence[IndexRow]) -> list[str]:
    """Ids with every link target inside the set before the record that links to it (Kahn's
    order); ties by `(created_at, id)`. Links point only to earlier records (plan 4.3), so an
    order always exists; skewed clocks cannot break it."""
    by_id = {row.id: row for row in rows}
    waiting = {row.id: {dst for _rel, dst in row.links if dst in by_id} for row in rows}
    order: list[str] = []
    while waiting:
        ready = sorted(
            (by_id[rid] for rid, deps in waiting.items() if not deps),
            key=lambda r: (r.created_at, r.id),
        )
        if not ready:  # a cycle cannot be built (ids hash their links); keep the rest by time
            ready = sorted((by_id[rid] for rid in waiting), key=lambda r: (r.created_at, r.id))
        for row in ready:
            order.append(row.id)
            del waiting[row.id]
        done = {row.id for row in ready}
        for deps in waiting.values():
            deps -= done
    return order


def export_lines(
    library: Library, ids: Iterable[str], refs: dict[str, str], keep_paths: bool
) -> list[bytes]:
    """The codec's lines for these records: raw verified envelopes only."""
    import decoy_engine
    from decoy_engine import records

    from decoy._version import __version__

    raws: list[Any] = []
    for rid in ids:
        found = library.get(rid)
        if isinstance(found, records.RecordNeedsNewer) and not found.verified:
            continue  # a later envelope major cannot be verified or rewritten by this version
        raws.append(found.raw)
    producer = {
        "name": "decoy-cli",
        "version": __version__,
        "engine_version": decoy_engine.__version__,
    }
    return list(
        records.export_lines(
            raws,
            producer=producer,
            exported_at=datetime.now(timezone.utc),
            refs=refs,
            keep_paths=keep_paths,
            logs=(),
        )
    )


def _say(state: OutputState, *parts: object) -> None:
    if state.mode is OutputMode.default:
        state.console.print(*parts, soft_wrap=True, markup=False, highlight=False)


def _notice(state: OutputState, *parts: object) -> None:
    state.err_console.print(warn("notice:"), *parts, markup=False, highlight=False)


def export_command(
    out: Path = typer.Option(
        ..., "--output", "-o", metavar="FILE", help="Write the export here (0600)."
    ),
    kind: str | None = typer.Option(None, "--kind", metavar="K", help="Only records of this kind."),
    since: str | None = typer.Option(
        None,
        "--since",
        metavar="D",
        help="Only records made at or after D (YYYY-MM-DD or ISO time).",
    ),
    ref: str | None = typer.Option(
        None,
        "--ref",
        metavar="R",
        help="Only R (a ref, id or KIND/latest) and every record it links to.",
    ),
    include_logs: bool = typer.Option(
        False, "--include-logs", help="Add the job logs of the exported runs (none exist yet)."
    ),
    keep_paths: bool = typer.Option(
        False,
        "--keep-paths",
        help="Keep paths as recorded and export every record byte for byte. Without it, paths are "
        "reduced to file names and records this version cannot strip are withheld.",
    ),
    library: Path | None = library_option(),
) -> None:
    """Export records as one self-verifying JSON Lines file the platform can import."""
    from decoy_engine.records import RecordError

    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._paths import LIBRARY
    from decoy.cli.library._read import _instant as parse_instant
    from decoy.cli.library._resolve import TargetError, resolve_target

    state = setup_output(False, False, False)
    cutoff: datetime | None = None
    if since is not None:
        try:
            cutoff = parse_instant(since)
        except ValueError:
            cutoff = None
        if cutoff is None:
            fail(state, "--since takes a date (YYYY-MM-DD) or an ISO time")
    root = root_or_fail(state, library)
    opened = open_or_fail(state, root.path)
    if not (root.path / LIBRARY).is_dir():
        fail(state, "there is no library to export here")
    target: str | None = None
    if ref is not None:
        problem: str | None = None
        try:
            target = resolve_target(opened, ref)
        except TargetError as exc:
            problem = str(exc)
        if problem is not None:
            fail(state, problem)
    ids, refs = select(opened, kind=kind, since=cutoff, ref=ref, target=target)
    caught: Exception | None = None
    lines: list[bytes] = []
    try:
        lines = export_lines(opened, ids, refs, keep_paths)
        from decoy.cli.library._fs import write_user_file

        write_user_file(out, b"".join(lines))
    except (LibraryError, RecordError) as exc:
        caught = exc
    if caught is not None:
        fail_library(state, caught)
    header = json.loads(lines[0])
    withheld = header.get("withheld_records") or []
    if withheld:
        _notice(
            state,
            f"withheld {len(withheld)} record(s) this version cannot strip: {', '.join(withheld)};",
            "rerun with --keep-paths to include them byte for byte",
        )
    if include_logs:
        _notice(state, "no job logs exist yet; none exported")
    _say(state, f"exported {header['record_count']} records to {out}")
    raise typer.Exit(code=EXIT_OK)
