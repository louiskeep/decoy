"""Shared shrink-only ratchet logic for sentry baselines (stdlib plus tomllib).

A baseline is a JSON file ``{"sentry_id", "created_in", "entries": {key: {"reason"}}}``
under ``tests/sentry/baselines/``. ``scripts/dev/sentry_registry.toml`` binds each sentry id to
exactly one baseline path. ``check`` compares the working tree with a base commit and returns
findings; an empty list means the ratchet holds. Messages carry ids, paths and keys only.

Ported from decoy-engine ``tests/sentry/_ratchet.py`` (X0a), plus the platform's
``created_in`` rules: every baseline names a non-empty ``created_in``, and a first inventory
must name the slice passed as ``slice_name`` when one is given.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REGISTRY = "scripts/dev/sentry_registry.toml"
BASELINE_DIR = "tests/sentry/baselines"
MIN_REASON = 15
PLACEHOLDERS = frozenset({"todo", "tbd", "fixme", "xxx", "n/a", "none"})


@dataclass(frozen=True)
class Baseline:
    sentry_id: str
    created_in: str  # as written; "" when missing or not a string
    keys: frozenset[str]
    reasons: dict[str, object]


def parse_registry(text: str) -> tuple[dict[str, str], list[str]]:
    """Return ``{id: path}`` and findings for duplicate ids or shared paths."""
    rows = tomllib.loads(text).get("sentry", [])
    out: dict[str, str] = {}
    findings: list[str] = []
    for row in rows:
        sid, path = row.get("id", ""), row.get("baseline", "")
        if sid in out:
            findings.append(f"registry: sentry id {sid} appears twice")
        out[sid] = path
    for path in sorted(set(out.values())):
        ids = sorted(i for i, p in out.items() if p == path)
        if len(ids) > 1:
            findings.append(f"registry: two sentries ({', '.join(ids)}) share baseline {path}")
        if not path.startswith(BASELINE_DIR + "/"):
            findings.append(f"registry: baseline {path} is outside {BASELINE_DIR}/")
    return out, findings


def parse_baseline(text: str) -> Baseline:
    data = json.loads(text)
    entries = data.get("entries", {})
    created_in = data.get("created_in")
    return Baseline(
        str(data.get("sentry_id", "")),
        created_in if isinstance(created_in, str) else "",
        frozenset(entries),
        entries,
    )


def reason_findings(path: str, base: Baseline) -> list[str]:
    out = []
    for key in sorted(base.keys):
        entry = base.reasons[key]
        reason = entry.get("reason") if isinstance(entry, dict) else None
        text = reason.strip() if isinstance(reason, str) else ""
        if len(text) < MIN_REASON or text.lower().strip(".!") in PLACEHOLDERS:
            out.append(
                f"{path}: reason for {key} is empty, a placeholder or under {MIN_REASON} chars"
            )
    return out


def _git_show(root: Path, ref: str, rel: str) -> str | None:
    res = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{rel}"],
        capture_output=True,
        text=True,
    )
    return res.stdout if res.returncode == 0 else None


def _base_keys(root: Path, ref: str, path: str) -> frozenset[str]:
    text = _git_show(root, ref, path)
    return parse_baseline(text).keys if text is not None else frozenset()


def _fmt(keys: frozenset[str]) -> str:
    return ", ".join(sorted(keys))


def check(root: Path, base_ref: str, slice_name: str | None = None) -> tuple[list[str], list[str]]:
    """Return ``(findings, report_lines)`` for the tree at ``root`` against ``base_ref``."""
    reg_file = root / REGISTRY
    head, findings = parse_registry(
        reg_file.read_text(encoding="utf-8") if reg_file.exists() else ""
    )
    base_text = _git_show(root, base_ref, REGISTRY)
    base_reg = parse_registry(base_text)[0] if base_text is not None else {}
    report: list[str] = []

    on_disk = {p.relative_to(root).as_posix() for p in (root / BASELINE_DIR).glob("*.json")}
    for path in sorted(on_disk - set(head.values())):
        findings.append(f"{path}: baseline file is not registered in {REGISTRY}")

    loaded: dict[str, Baseline] = {}
    for sid, path in sorted(head.items()):
        file = root / path
        if not file.exists():
            findings.append(f"{sid}: registry points at {path} but there is no baseline file")
            continue
        loaded[sid] = base = parse_baseline(file.read_text(encoding="utf-8"))
        if base.sentry_id != sid:
            findings.append(
                f"{path}: sentry_id {base.sentry_id!r} does not match registry id {sid}"
            )
        if not base.created_in.strip():
            findings.append(f"{path}: created_in is missing or not a non-empty string")
        findings += reason_findings(path, base)

    removed = set(base_reg) - set(head)
    old_union: frozenset[str] = frozenset().union(
        *(_base_keys(root, base_ref, base_reg[s]) for s in removed)
    )
    new_union: frozenset[str] = frozenset()
    for sid, base in sorted(loaded.items()):
        path = head[sid]
        report.append(f"{sid}: {len(base.keys)} key(s) in {path}")
        if sid in base_reg:
            if base_reg[sid] != path:
                findings.append(f"{sid}: baseline moved from {base_reg[sid]} to {path}")
                continue
            grown = base.keys - _base_keys(root, base_ref, path)
            if grown:
                findings.append(
                    f"{sid}: baseline gained key(s) not in the merge base: {_fmt(grown)}"
                )
        elif removed:
            new_union |= base.keys
        else:
            # Newly registered in this diff: the one way a first inventory is admitted.
            report.append(f"{sid}: first inventory, {len(base.keys)} key(s), review required")
            if slice_name is not None and base.created_in != slice_name:
                findings.append(
                    f"{sid}: created_in {base.created_in!r} is not slice {slice_name!r}"
                )
    grown = new_union - old_union
    if removed and grown:
        findings.append(
            f"replacement or split of {_fmt(frozenset(removed))} adds key(s): {_fmt(grown)}"
        )
    return findings, report
