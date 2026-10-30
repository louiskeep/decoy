"""Bounded exact-literal scan of the Git INDEX (what would be committed).

The scan reads stage-0 blobs by object id through `git cat-file`; it never opens a
worktree path, so a clean worktree cannot hide a dirty index nor the reverse. Matching is
exact byte search of customer-authored literals over the whole staged post-image: no
regex, entropy, case folding, or built-in detector. Reports carry rule/pattern ids,
repo-relative paths, a first-hit region, and a count -- never the literal or the line.

Prior art: `git diff --cached` as "what would be committed" (git-diff docs), NUL-delimited
plumbing (`-z`, `ls-files -z`, `cat-file --batch`) so filenames are never parsed from
human text, and the pre-commit provider contract (`pass_filenames: false` so worktree
filenames never become the scan source).

Hard limits are maxima defined in `contracts` (a manifest may lower them, never raise).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from decoy.ci._git import GitBudget, GitFailure, run_git
from decoy.ci.contracts import (
    SafeFinding,
    SourceLocation,
    StagedPattern,
    StagedScan,
    UnsafeFindingError,
)
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RUNTIME, EXIT_USAGE

__all__ = [
    "GitBudget",
    "StagedEntry",
    "StagedResult",
    "glob_matches",
    "parse_name_status_z",
    "read_staged_entries",
    "scan_staged",
]

CHECK_ID = "staged_scan"
_REGULAR_MODES = {"100644", "100755"}
_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SCANNED = {"A", "C", "M", "R", "T"}
_COUNT_CAP = 1_000_000


# ---------------------------------------------------------------------------
# Glob scope (repo-root relative; `*`, `**`, `?` only)
# ---------------------------------------------------------------------------


def _segment_regex(segment: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "*":
            while i + 1 < len(segment) and segment[i + 1] == "*":
                i += 1
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


def _glob_regex(glob: str) -> re.Pattern[str]:
    parts = glob.split("/")
    out: list[str] = []
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if seg == "**":
            out.append(".+" if last else "(?:[^/]+/)*")
        else:
            out.append(_segment_regex(seg) + ("" if last else "/"))
    return re.compile("".join(out) + r"\Z", re.DOTALL)


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_matches(glob: str, path: str) -> bool:
    rx = _GLOB_CACHE.get(glob)
    if rx is None:
        rx = _GLOB_CACHE[glob] = _glob_regex(glob)
    return rx.match(path) is not None


def _in_scope(pattern: StagedPattern, path: str) -> bool:
    if not any(glob_matches(g, path) for g in pattern.paths):
        return False
    return not any(glob_matches(g, path) for g in pattern.exclude_paths)


# ---------------------------------------------------------------------------
# Git plumbing
# ---------------------------------------------------------------------------


def parse_name_status_z(raw: bytes) -> list[tuple[str, bytes]]:
    """Parse `git diff --name-status -z` into (status letter, post-image path).

    A/M/D/T/U carry one path field; R and C carry TWO (`R100\\0old\\0new\\0`), and the
    post-image is the second. Reading a fixed number of fields per status keeps the
    stream aligned after a rename.
    """
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    out: list[tuple[str, bytes]] = []
    i = 0
    while i < len(fields):
        status = fields[i].decode("ascii", "replace")
        if not status or not status[0].isalpha() or not status[0].isupper():
            raise ValueError("unrecognised name-status record")
        letter = status[0]
        width = 2 if letter in ("R", "C") else 1
        if i + 1 + width > len(fields):
            raise ValueError("truncated name-status record")
        out.append((letter, fields[i + width]))
        i += 1 + width
    return out


@dataclass(frozen=True)
class StagedEntry:
    path: bytes
    status: str
    blob_id: str
    mode: str


def _changed(root: Path, budget: GitBudget) -> list[tuple[str, bytes]]:
    raw = run_git(
        ["diff", "--cached", "--name-status", "-z", "-M", "--no-ext-diff", "--no-textconv"],
        root,
        budget,
    )
    try:
        return parse_name_status_z(raw)
    except ValueError as exc:
        raise GitFailure("unparseable name-status output") from exc


def _stage_zero(root: Path, budget: GitBudget, paths: list[bytes]) -> dict[bytes, tuple[str, str]]:
    """{path: (mode, blob id)} for stage-0 index entries of exactly these paths."""
    if not paths:
        return {}
    argv = ["ls-files", "--stage", "-z", "--", *[os.fsdecode(p) for p in paths]]
    raw = run_git(argv, root, budget)
    found: dict[bytes, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) != 3:
            raise GitFailure("unparseable ls-files output")
        mode, oid, stage = (p.decode("ascii", "replace") for p in parts)
        if stage != "0":
            raise GitFailure("unmerged index entry")
        if not _OID.match(oid):
            raise GitFailure("unexpected object id")
        found[path] = (mode, oid)
    return found


def read_staged_entries(root: Path, budget: GitBudget) -> list[StagedEntry]:
    """Every A/C/M/R/T staged path with its stage-0 blob id (no scope filtering)."""
    changed = [(s, p) for s, p in _changed(root, budget) if s in _SCANNED]
    index = _stage_zero(root, budget, [p for _, p in changed])
    entries: list[StagedEntry] = []
    for status, path in changed:
        if path not in index:
            raise GitFailure("staged path has no stage-0 entry")
        mode, oid = index[path]
        entries.append(StagedEntry(path, status, oid, mode))
    return entries


def _blob_sizes(root: Path, budget: GitBudget, oids: list[str]) -> dict[str, int]:
    if not oids:
        return {}
    raw = run_git(
        ["cat-file", "--batch-check"], root, budget, stdin=("\n".join(oids) + "\n").encode()
    )
    sizes: dict[str, int] = {}
    lines = raw.decode("ascii", "replace").splitlines()
    if len(lines) != len(oids):
        raise GitFailure("unexpected cat-file --batch-check output")
    for oid, line in zip(oids, lines):
        bits = line.split(" ")
        if len(bits) != 3 or bits[0] != oid or bits[1] != "blob" or not bits[2].isdigit():
            raise GitFailure("object is not a readable blob")
        sizes[oid] = int(bits[2])
    return sizes


def _read_blobs(root: Path, budget: GitBudget, oids: list[str]) -> dict[str, bytes]:
    if not oids:
        return {}
    raw = run_git(["cat-file", "--batch"], root, budget, stdin=("\n".join(oids) + "\n").encode())
    blobs: dict[str, bytes] = {}
    pos = 0
    for oid in oids:
        end = raw.find(b"\n", pos)
        if end < 0:
            raise GitFailure("truncated cat-file --batch output")
        bits = raw[pos:end].decode("ascii", "replace").split(" ")
        if len(bits) != 3 or bits[0] != oid or bits[1] != "blob" or not bits[2].isdigit():
            raise GitFailure("unexpected cat-file --batch header")
        size = int(bits[2])
        start = end + 1
        blobs[oid] = raw[start : start + size]
        if len(blobs[oid]) != size:
            raise GitFailure("truncated blob")
        pos = start + size + 1  # trailing LF after each object
    return blobs


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@dataclass
class StagedResult:
    status: str  # ok | noop | findings | partial | failed
    reason_code: str | None
    exit_code: int
    findings: list[SafeFinding] = field(default_factory=list)
    # Raw prose for the unsafe debug sink ONLY; emitters never see this field.
    raw: list[str] = field(default_factory=list)


def _decode_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _first_hit_location(uri: str, data: bytes, literal: bytes) -> SourceLocation:
    if not _decode_text(data):
        return SourceLocation(uri=uri)
    pos = data.find(literal)
    line = data.count(b"\n", 0, pos) + 1
    line_start = data.rfind(b"\n", 0, pos) + 1
    column = len(data[line_start:pos].decode("utf-8")) + 1
    width = len(literal.decode("utf-8"))
    return SourceLocation(
        uri=uri, start_line=line, start_column=column, end_line=line, end_column=column + width
    )


def scan_staged(root: Path, scan: StagedScan) -> StagedResult:
    limits = scan.limits
    budget = GitBudget(limits.max_git_seconds)
    try:
        return _scan(root, scan, budget)
    except GitFailure as exc:
        return StagedResult("failed", "ci.git_failure", EXIT_RUNTIME, raw=[exc.raw])


def _scan(root: Path, scan: StagedScan, budget: GitBudget) -> StagedResult:
    limits = scan.limits
    changed = _changed(root, budget)
    if any(status == "U" for status, _ in changed):
        return StagedResult("partial", "ci.staged_unmerged", EXIT_USAGE)

    candidates: list[tuple[str, bytes]] = []
    unsupported = False
    for status, path in changed:
        if status == "D":
            continue
        if status not in _SCANNED:
            unsupported = True
            continue
        candidates.append((status, path))

    scoped: dict[bytes, list[StagedPattern]] = {}
    for _, path in candidates:
        text = os.fsdecode(path)
        hits = [p for p in scan.patterns if _in_scope(p, text)]
        if hits:
            scoped[path] = hits
    if not scoped and not unsupported:
        return StagedResult("noop", "ci.no_staged_files", EXIT_OK)

    limit_hit = False
    ordered = sorted(scoped)
    if len(ordered) > limits.max_files:
        limit_hit = True
        ordered = ordered[: limits.max_files]

    index = _stage_zero(root, budget, ordered)
    readable: list[bytes] = []
    for path in ordered:
        if path not in index:
            raise GitFailure("staged path has no stage-0 entry")
        mode, _ = index[path]
        if mode not in _REGULAR_MODES:
            unsupported = True  # symlink or submodule: never followed
            continue
        readable.append(path)

    sizes = _blob_sizes(root, budget, sorted({index[p][1] for p in readable}))
    take: list[bytes] = []
    total = 0
    for path in readable:
        size = sizes[index[path][1]]
        if size > limits.max_blob_bytes or total + size > limits.max_total_bytes:
            limit_hit = True
            continue
        total += size
        take.append(path)
    blobs = _read_blobs(root, budget, sorted({index[p][1] for p in take}))

    groups: list[SafeFinding] = []
    for path in take:
        data = blobs[index[path][1]]
        uri = os.fsdecode(path)
        for pattern in scoped[path]:
            literal = pattern.literal.encode("utf-8")
            count = data.count(literal)
            if count == 0:
                continue
            try:
                groups.append(
                    SafeFinding.create(
                        rule_id=f"staged.{pattern.id}",
                        level="error",
                        safe_message_id="ci.staged_pattern_match",
                        check_id=CHECK_ID,
                        location=_first_hit_location(uri, data, literal),
                        occurrences=min(count, _COUNT_CAP),
                    )
                )
            except UnsafeFindingError:
                # A hit in a path that cannot be reported safely (e.g. a backslash in the
                # name) must still block: refuse as unsupported rather than drop it.
                unsupported = True
    groups.sort(key=SafeFinding.sort_key)
    if len(groups) > limits.max_finding_groups:
        limit_hit = True
        groups = groups[: limits.max_finding_groups]

    if unsupported:
        return StagedResult("partial", "ci.staged_unsupported_entry", EXIT_USAGE, groups)
    if limit_hit:
        return StagedResult("partial", "ci.staged_scan_limit", EXIT_USAGE, groups)
    if groups:
        return StagedResult("findings", None, EXIT_FINDINGS, groups)
    return StagedResult("ok", None, EXIT_OK)
