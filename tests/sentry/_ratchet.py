"""Shared shrink-only ratchet logic for sentry baselines (stdlib plus tomllib).

A baseline is a JSON file ``{"sentry_id", "created_in", "entries": {key: {"reason"}}}``
under ``tests/sentry/baselines/``. ``scripts/dev/sentry_registry.toml`` binds each sentry id to
exactly one baseline path. ``check`` compares the working tree with a base commit and returns
findings; an empty list means the ratchet holds. An entry that carries a numeric ceiling
(``max``, ``count`` or ``sites``, each on its own) may keep or lower it, never raise or drop it (see
``max_raised``). Messages carry ids, paths and keys only. ``load_allowlist`` is the one reader a
sentry uses for its allowlist: the registered baseline JSON, which is the only copy.

Growth has one recorded path: a registry row may list ``approved_growth`` entries, each an exact
key and a dated owner decision ``owner YYYY-MM-DD <text>``. Ported from decoy-engine
``tests/sentry/_ratchet.py`` (``DECISION``, ``parse_approvals`` and the stale-row check) and its
``scripts/dev/sentry_registry.toml`` rows. A listed key may be added; a pattern, a bad decision, or
a key the baseline does not hold is a finding.

Ported from decoy-engine ``tests/sentry/_ratchet.py`` (X0a), plus the platform's
``created_in`` rules: every baseline names a non-empty ``created_in``, and a first inventory
must name the slice passed as ``slice_name`` when one is given.

A code move renames baseline keys without adding anything. A baseline may carry a top-level
``"moved_from": {new_key: old_key}`` map. A gained key is admitted only when the map names an
old key that was in the merge base, is gone from the head, is named once, and whose base entry
equals the new head entry exactly. An entry whose new key is already in the base is a leftover
of a merged move and is ignored. The map is top-level, not inside an entry, because other
sentries compare entries exactly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REGISTRY = "scripts/dev/sentry_registry.toml"
BASELINE_DIR = "tests/sentry/baselines"
MIN_REASON = 15
PLACEHOLDERS = frozenset({"todo", "tbd", "fixme", "xxx", "n/a", "none"})
# Numeric fields a baseline entry may carry as a count the ratchet lets only fall, each checked.
CEILING_FIELDS = ("max", "count", "sites")


def _load_decision_check():
    """The one dated-owner-decision grammar lives in shipped code; load it by path (stdlib only)."""
    path = Path(__file__).resolve().parents[2] / "src/decoy/distribution/release_identity.py"
    spec = importlib.util.spec_from_file_location("_release_identity_for_ratchet", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.is_dated_owner_decision


_decision_ok = _load_decision_check()
_GLOB_CHARS = frozenset("*?[]")


@dataclass(frozen=True)
class Baseline:
    sentry_id: str
    created_in: str  # as written; "" when missing or not a string
    keys: frozenset[str]
    reasons: dict[str, object]
    moved_from: object = None  # raw top-level map; validated in ``move_findings``


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


def load_allowlist(sentry_id: str, root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The entries of the baseline the registry names for ``sentry_id``: ``{key: entry}``."""
    base = root if root is not None else Path(__file__).resolve().parents[2]
    registered, _ = parse_registry((base / REGISTRY).read_text(encoding="utf-8"))
    doc = json.loads((base / registered[sentry_id]).read_text(encoding="utf-8"))
    return dict(doc["entries"])


def parse_approvals(text: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """``{sentry id: {key: decision}}`` from ``approved_growth`` rows, and findings for bad rows.

    A row is ``{ key, decision }``; the key compares exactly (no glob or prefix) and the decision
    must name a dated owner decision. Growth of a baseline passes only through a row here.
    """
    out: dict[str, dict[str, str]] = {}
    findings: list[str] = []
    for row in tomllib.loads(text).get("sentry", []):
        sid = row.get("id", "")
        for item in row.get("approved_growth", []):
            key = item.get("key") if isinstance(item, dict) else None
            decision = item.get("decision") if isinstance(item, dict) else None
            if not isinstance(key, str) or not key:
                findings.append(f"{sid}: approved_growth row has no key")
            elif _GLOB_CHARS & set(key):
                findings.append(f"{sid}: approved_growth key {key} is a pattern; list exact keys")
            elif not _decision_ok(decision):
                findings.append(
                    f"{sid}: approved_growth for {key} needs a decision "
                    "'owner YYYY-MM-DD <text of 10+ chars>'"
                )
            else:
                out.setdefault(sid, {})[key] = decision
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
        data.get("moved_from"),
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


def _base_entries(root: Path, ref: str, path: str) -> dict[str, object]:
    text = _git_show(root, ref, path)
    return dict(parse_baseline(text).reasons) if text is not None else {}


def _int_field(entry: dict[str, object], field: str) -> int | None:
    value = entry.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def max_raised(head: object, base: object) -> bool:
    """True when the ceiling of an entry rose, was dropped, or moved to another field.

    Each ceiling field (``max``, ``count``, ``sites``) the base entry holds as an integer is
    checked on its own. An entry that had a ceiling may not gain a ceiling field it did not have:
    lowering ``count`` while adding ``max`` would move the cap to the new field.
    """
    if not isinstance(base, dict):
        return False
    held = [f for f in CEILING_FIELDS if _int_field(base, f) is not None]
    if not held:
        return False
    head_entry = head if isinstance(head, dict) else {}
    if any(_int_field(head_entry, f) is not None for f in CEILING_FIELDS if f not in held):
        return True
    for field in held:
        old, new = _int_field(base, field), _int_field(head_entry, field)
        if old is not None and (new is None or new > old):
            return True
    return False


def _base_baseline(root: Path, ref: str, path: str) -> Baseline | None:
    text = _git_show(root, ref, path)
    return parse_baseline(text) if text is not None else None


def move_findings(
    path: str, head: Baseline, base: Baseline | None, gained: frozenset[str]
) -> tuple[list[str], frozenset[str]]:
    """Validate ``moved_from`` against the base; return findings and the admitted new keys."""
    raw = head.moved_from
    if raw is None:
        return [], frozenset()
    if not isinstance(raw, dict):
        return [f"{path}: moved_from is not an object"], frozenset()
    findings: list[str] = []
    admitted: set[str] = set()
    base_keys = base.keys if base is not None else frozenset()
    base_entries = base.reasons if base is not None else {}
    named_olds: dict[str, str] = {}
    for new, old in sorted(raw.items(), key=lambda kv: str(kv[0])):
        if (
            not isinstance(new, str)
            or not isinstance(old, str)
            or not new.strip()
            or not old.strip()
        ):
            findings.append(f"{path}: moved_from needs non-empty string keys and values")
            continue
        if old in named_olds:
            findings.append(f"{path}: moved_from names {old} for both {named_olds[old]} and {new}")
            continue
        named_olds[old] = new
        if new not in head.keys:
            findings.append(f"{path}: moved_from key {new} is not an entry in the head")
        elif new not in gained:
            continue  # the move already merged: the key is in the base, so it admits nothing
        elif old not in base_keys:
            findings.append(f"{path}: moved_from old key {old} was not in the merge base")
        elif old in head.keys:
            findings.append(f"{path}: moved_from old key {old} is still in the head")
        elif base_entries[old] != head.reasons[new]:
            findings.append(f"{path}: moved entry {new} differs from {old} in the merge base")
        else:
            admitted.add(new)
    return findings, frozenset(admitted)


def _fmt(keys: frozenset[str]) -> str:
    return ", ".join(sorted(keys))


def check(root: Path, base_ref: str, slice_name: str | None = None) -> tuple[list[str], list[str]]:
    """Return ``(findings, report_lines)`` for the tree at ``root`` against ``base_ref``."""
    reg_file = root / REGISTRY
    reg_text = reg_file.read_text(encoding="utf-8") if reg_file.exists() else ""
    head, findings = parse_registry(reg_text)
    approvals, approval_findings = parse_approvals(reg_text)
    findings += approval_findings
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
        findings += [
            f"{sid}: stale approved_growth, {key} is not in {path}"
            for key in sorted(set(approvals.get(sid, {})) - base.keys)
        ]

    removed = set(base_reg) - set(head)
    # A key a replacement keeps must keep its max too, or a rename would launder a raised max.
    old_entries: dict[str, list[object]] = {}
    for s in removed:
        for key, entry in _base_entries(root, base_ref, base_reg[s]).items():
            old_entries.setdefault(key, []).append(entry)
    old_union = frozenset(old_entries)
    new_union: frozenset[str] = frozenset()
    replaced_raised: set[str] = set()
    for sid, base in sorted(loaded.items()):
        path = head[sid]
        report.append(f"{sid}: {len(base.keys)} key(s) in {path}")
        if sid in base_reg:
            if base_reg[sid] != path:
                findings.append(f"{sid}: baseline moved from {base_reg[sid]} to {path}")
                continue
            base_doc = _base_baseline(root, base_ref, path)
            grown = base.keys - (base_doc.keys if base_doc is not None else frozenset())
            moved_f, admitted = move_findings(path, base, base_doc, grown)
            findings += moved_f
            grown -= admitted
            approved = grown & frozenset(approvals.get(sid, {}))
            report += [
                f"{sid}: approved growth {k} ({approvals[sid][k]})" for k in sorted(approved)
            ]
            grown -= approved
            if grown:
                findings.append(
                    f"{sid}: baseline gained key(s) not in the merge base: {_fmt(grown)}"
                )
            old = base_doc.reasons if base_doc is not None else {}
            raised = sorted(
                k for k in base.keys & old.keys() if max_raised(base.reasons[k], old[k])
            )
            if raised:
                findings.append(f"{sid}: max raised or dropped for key(s): {', '.join(raised)}")
        elif removed:
            new_union |= base.keys
            replaced_raised |= {
                k
                for k in base.keys & old_union
                if any(max_raised(base.reasons[k], old) for old in old_entries[k])
            }
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
    if replaced_raised:
        findings.append(
            f"replacement or split of {_fmt(frozenset(removed))} raised or dropped max for"
            f" key(s): {_fmt(frozenset(replaced_raised))}"
        )
    return findings, report
