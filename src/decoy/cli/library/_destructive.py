"""`decoy library prune` and `decoy library clean` (plan 4.7, 4.15; L4b).

The destructive-operation rule: resolve the exact targets read-only first and print them; delete
only with `--yes`. `prune` touches record objects (and their index rows) only; `clean` touches
`.decoy/scratch/` only. Neither ever reaches a vault file, key, target, `out/` run folder or
anything outside the library root. A file that cannot be removed (held open on Windows) is listed
as left behind and the command exits 4 (`EXIT_FINDINGS`).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK
from decoy.cli.library._cli import fail, fail_library, library_option, open_or_fail, root_or_fail
from decoy.ui.output import OutputMode, OutputState, setup_output

__all__ = ["clean_command", "prune_command"]

_DURATION = re.compile(r"([0-9]{1,6})([dhm])")
_UNIT = {"d": "days", "h": "hours", "m": "minutes"}


def _say(state: OutputState, *parts: object) -> None:
    if state.mode is OutputMode.default:
        state.console.print(*parts, soft_wrap=True, markup=False, highlight=False)


def _duration(state: OutputState, text: str) -> timedelta:
    found = _DURATION.fullmatch(text)
    if found is None:
        fail(state, "--older-than takes a number and d, h or m, for example 90d")
    return timedelta(**{_UNIT[found.group(2)]: int(found.group(1))})


def prune_command(
    kind: str | None = typer.Option(None, "--kind", metavar="K", help="Only records of this kind."),
    keep_last: int | None = typer.Option(
        None, "--keep-last", metavar="N", help="Keep the newest N records of each kind."
    ),
    older_than: str | None = typer.Option(
        None, "--older-than", metavar="D", help="Only records older than D (90d, 12h, 30m)."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Delete. Without it, prune only shows what it would delete."
    ),
    library: Path | None = library_option(),
) -> None:
    """Delete records you no longer keep. Never one a ref or a kept record links to, one younger
    than an hour, or one of a kind this Decoy does not know. With no options, applies the
    `keep_last` rules in `.decoy/library.yaml`."""
    from decoy.cli.library import _prune
    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._paths import LIBRARY

    state = setup_output(False, False, False)
    if keep_last is not None and keep_last < 0:
        fail(state, "--keep-last takes 0 or more")
    age = None if older_than is None else _duration(state, older_than)
    root = root_or_fail(state, library)
    opened = open_or_fail(state, root.path)
    if not (root.path / LIBRARY).is_dir():
        _say(state, "no library at", str(root.path))
        raise typer.Exit(code=EXIT_OK)
    caught: LibraryError | None = None
    rules: list = []
    try:
        if kind is None and keep_last is None and age is None:
            rules = _prune.policy_rules(root.path)
        else:
            rules = [_prune.Rule(kind=kind, keep_last=keep_last, older_than=age)]
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        fail_library(state, caught)
    if not rules:
        _say(state, "nothing to prune: the policy keeps every record")
        raise typer.Exit(code=EXIT_OK)
    now = datetime.now(timezone.utc)
    try:
        if not yes:
            plan = _prune.prune_preview(opened, rules, now=now)
        else:
            report = _prune.prune_apply(opened, rules, now=now)
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        fail_library(state, caught)
    if not yes:
        for rid in plan.delete:
            _say(state, "would delete", rid)
        _say(
            state,
            f"{len(plan.delete)} to delete, {len(plan.protected)} kept by a ref or a link, "
            f"{len(plan.young)} younger than an hour; rerun with --yes to delete",
        )
        raise typer.Exit(code=EXIT_OK)
    for rid in report.deleted:
        _say(state, "deleted", rid)
    for rid in report.left:
        _say(state, "left behind", rid)
    _say(state, f"{len(report.deleted)} deleted, {len(report.left)} left behind")
    raise typer.Exit(code=EXIT_FINDINGS if report.left else EXIT_OK)


def clean_command(
    yes: bool = typer.Option(
        False, "--yes", help="Delete. Without it, clean only shows what it would delete."
    ),
    library: Path | None = library_option(),
) -> None:
    """Delete everything in `.decoy/scratch/` (sample output and staging). Records, logs and
    anything outside the library are never touched."""
    from decoy.cli.library._errors import LIBRARY_LOCK_UNAVAILABLE, LibraryError
    from decoy.cli.library._paths import SCRATCH
    from decoy.cli.library._scratch import clean_all

    state = setup_output(False, False, False)
    root = root_or_fail(state, library)
    opened = open_or_fail(state, root.path)
    scratch = root.path / SCRATCH
    entries = sorted(scratch.iterdir()) if scratch.is_dir() else []
    if not entries:
        _say(state, "scratch is empty")
        raise typer.Exit(code=EXIT_OK)
    if opened.degraded is not None:
        fail_library(state, LibraryError(LIBRARY_LOCK_UNAVAILABLE))
    if not yes:
        for entry in entries:
            _say(state, "would delete", f"{SCRATCH}/{entry.name}")
        _say(state, f"{len(entries)} to delete; rerun with --yes to delete")
        raise typer.Exit(code=EXIT_OK)
    caught: LibraryError | None = None
    results: list = []
    try:
        results = clean_all(opened)
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        fail_library(state, caught)
    left = 0
    for name, report in results:
        _say(state, "deleted", f"{SCRATCH}/{name}", f"({report.removed} files)")
        for skipped in report.skipped:
            left += 1
            _say(state, "left behind", f"{SCRATCH}/{name}/{skipped}")
    raise typer.Exit(code=EXIT_FINDINGS if left else EXIT_OK)
