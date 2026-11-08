"""The stored failing-id baseline of scripts/dev/gates.sh: its model and run mode.

Ported from the engine's scripts/dev/_gates_baseline.py (ENGINE-PAR P1); the CLI keeps its own
copy and the build record lists the differences. `load_baseline` is the only place that reads
the JSON file, so no consumer sees an unvalidated field. `check_stored` decides whether a run
may be compared with a stored file. Stdlib only, so it runs in any venv; `_gates_report.py` is
the entry point and re-exports these names."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# How a baseline was produced. A compare is only meaningful against a baseline written the same
# way, so these fields travel with the file and `check_stored` refuses any difference.
MODE_KEYS = ("workers", "dist", "platform", "order")
# The stored file's layout version; bump it when a field changes meaning or is added.
FORMAT_VERSION = 1
# A stored SHA names one commit. A symbolic ref or a short prefix would pass `git cat-file` and
# could name a different commit later, so only the full lowercase form is accepted (D10).
_FULL_SHA = re.compile(r"[0-9a-f]{40}")


def order_label(order_seconds: dict[str, float]) -> str:
    """`collection` for an empty map, else a hash of the canonical map the order was built from."""
    if not order_seconds:
        return "collection"
    canon = json.dumps(order_seconds, sort_keys=True, separators=(",", ":"))
    return "file-seconds:" + hashlib.sha256(canon.encode()).hexdigest()


def run_mode(workers: int, order_seconds: dict[str, float]) -> dict[str, object]:
    return {
        "workers": workers,
        "dist": "no" if workers == 1 else "loadfile",
        "platform": f"{sys.platform}-{platform.machine()}",
        "order": order_label(order_seconds),
    }


class BaselineError(ValueError):
    """A stored baseline that may not be compared; the message says why and what to do."""


@dataclass(frozen=True)
class Baseline:
    """The one model of a stored baseline file: every reader loads it, the writer serializes it.

    `load_baseline` is the only place that reads the JSON, so no consumer sees an unvalidated
    field (a JSON `true` is not a count, a mode field is not a guess)."""

    repo: str
    main_sha: str
    head_sha: str
    collected: int
    skipped: int
    failing: tuple[str, ...]
    workers: int
    dist: str
    platform: str
    order: str
    order_seconds: dict[str, float]
    file_seconds: dict[str, float]

    def mode(self) -> dict[str, object]:
        return {k: getattr(self, k) for k in MODE_KEYS}

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["failing"] = sorted(self.failing)
        return {"format_version": FORMAT_VERSION, **data}


_FIELDS = tuple(Baseline.__dataclass_fields__)


def _is_count(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _is_sha(v: object) -> bool:
    return isinstance(v, str) and _FULL_SHA.fullmatch(v) is not None


def _is_seconds_map(v: object) -> bool:
    return isinstance(v, dict) and all(
        isinstance(k, str)
        and isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and x >= 0
        for k, x in v.items()
    )


def _parse_baseline(raw: object) -> Baseline:
    if not isinstance(raw, dict):
        raise BaselineError("the stored baseline is not a JSON object; rewrite the baseline")
    version = raw.get("format_version")
    if not _is_count(version) or version != FORMAT_VERSION:
        raise BaselineError(
            f"the stored baseline has format_version {version!r}, this gates.sh reads "
            f"format_version {FORMAT_VERSION}; rewrite the baseline"
        )
    missing = [k for k in _FIELDS if k not in raw]
    if missing:
        raise BaselineError(
            f"the stored baseline has no {', '.join(missing)}; rewrite the baseline"
        )
    extra = sorted(set(raw) - set(_FIELDS) - {"format_version"})
    if extra:
        raise BaselineError(
            f"the stored baseline has unknown field(s) {', '.join(extra)}; rewrite the baseline"
        )
    checks = {
        "repo": isinstance(raw["repo"], str),
        "main_sha": _is_sha(raw["main_sha"]),
        "head_sha": _is_sha(raw["head_sha"]),
        "collected": _is_count(raw["collected"]),
        "skipped": _is_count(raw["skipped"]),
        "failing": isinstance(raw["failing"], list)
        and all(isinstance(t, str) for t in raw["failing"]),
        "workers": _is_count(raw["workers"]) and raw["workers"] >= 1,
        "dist": isinstance(raw["dist"], str),
        "platform": isinstance(raw["platform"], str),
        "order": isinstance(raw["order"], str),
        "order_seconds": _is_seconds_map(raw["order_seconds"]),
        "file_seconds": _is_seconds_map(raw["file_seconds"]),
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise BaselineError(
            f"the stored baseline's {', '.join(bad)} has the wrong type or shape; "
            "rewrite the baseline"
        )
    fields = {k: raw[k] for k in _FIELDS}
    fields["failing"] = tuple(raw["failing"])
    return Baseline(**fields)


def load_baseline(path: Path) -> Baseline:
    readable, raw = True, None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        readable = False
    # Raised after the except block closes: inside it the parser's message, which can quote the
    # stored text, would ride along as __context__ even with `from None`.
    if not readable:
        raise BaselineError("the stored baseline is not readable JSON; rewrite the baseline")
    return _parse_baseline(raw)


def dump_baseline(path: Path, baseline: Baseline) -> None:
    """Write `baseline` only if `load_baseline` would accept it, so the writer cannot store a file
    the gate refuses (a short SHA, a negative count)."""
    data = baseline.to_json()
    _parse_baseline(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def stored_failing_under(path: Path, prefixes: list[str]) -> bool:
    """True when a stored failing id starts with any prefix (a test file path or a directory)."""
    return any(t.startswith(p) for t in load_baseline(path).failing for p in prefixes)


def _tree_of(root: Path, sha: str) -> str | None:
    """The tree id of commit `sha` in the repository at `root`, None when it does not resolve."""
    if not _FULL_SHA.fullmatch(sha):  # also keeps a leading "-" from reaching git as an option
        return None
    done = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{sha}^{{tree}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def provenance_problems(stored: Baseline, root: Path, require_main: bool = False) -> list[str]:
    """Why `head_sha` is not the commit this baseline was produced from (empty when it is).

    A producer writes a baseline only for a head whose tree equals main's tree, so a stored
    `head_sha` that is missing from the repository or has another tree is an accidental
    mismatch (a file from another checkout, a hand-edited field). This guards against that, not
    against someone forging the JSON: the V1 threat model is accidental leaks, so there is no
    signature. An unknown `main_sha` is left to the staleness check, which names it, unless
    `require_main` (the writer) wants it resolved.

    A baseline records head_sha == main_sha by construction (a carried file moves both). A
    different head is accepted only when it resolves and shares main's tree, as a promote of a
    squash-merged head does."""
    for name in ("main_sha", "head_sha"):
        if not _is_sha(getattr(stored, name)):
            return [f"{name} {getattr(stored, name)!r} is not a full 40-character lowercase SHA"]
    if stored.head_sha == stored.main_sha and not require_main:
        return []
    main_tree = _tree_of(root, stored.main_sha)
    if main_tree is None:
        return [f"main_sha {stored.main_sha} is not in this repository"] if require_main else []
    head_tree = _tree_of(root, stored.head_sha)
    if head_tree is None:
        return [f"head_sha {stored.head_sha} is not in this repository"]
    if head_tree != main_tree:
        return [f"head_sha {stored.head_sha} does not have the tree of main_sha {stored.main_sha}"]
    return []


def check_stored(path: Path, repo: str, workers: int, root: Path) -> list[str]:
    """Reasons this run may not be compared with the stored baseline (empty when it may).

    The CLI suite always runs serial in collection order, so a stored file in any other order,
    including one ordered by a map, is refused: this gates.sh has no order hook to match it."""
    try:
        stored = load_baseline(path)
    except BaselineError as exc:
        return [str(exc)]
    if stored.repo != repo:
        return [f"the stored baseline is for repo {stored.repo!r}, this run is {repo!r}"]
    if problems := provenance_problems(stored, root):
        return [f"{problems[0]}; rewrite the baseline"]
    theirs = stored.mode()
    mine = run_mode(workers, {})
    diff = [k for k in MODE_KEYS if theirs[k] != mine[k]]
    if stored.order_seconds and "order" not in diff:
        diff.append("order")  # a map under the `collection` label: the file contradicts itself
    if not diff:
        return []
    return [
        f"run mode differs in {', '.join(diff)}: baseline {json.dumps(theirs)}, "
        f"this run {json.dumps(mine)}; rewrite the baseline in this mode"
    ]


# A parametrize id from an object without __repr__ carries a memory address that changes every
# run, so a stored copy would never match. The engine refuses these at collection; the CLI write
# refuses them instead (D8). A literal hex parameter such as 0xdeadbeef is not an address.
_ADDRESS_ID = re.compile(r" at 0x[0-9a-fA-F]+>")


class WriteRefused(ValueError):
    """The baseline cannot be stored; the message says why. Nothing is written."""


def store_baseline(path: Path, baseline: Baseline, root: Path) -> None:
    """Write `baseline` after every writer-side refusal: addressed ids, provenance, the model."""
    if addressed := [t for t in baseline.failing if _ADDRESS_ID.search(t)]:
        raise WriteRefused(
            f"{len(addressed)} failing id(s) carry a memory address that changes every run: "
            + "; ".join(addressed)
        )
    if problems := provenance_problems(baseline, root, require_main=True):
        raise WriteRefused(problems[0])
    refusal = None
    try:
        dump_baseline(path, baseline)
    except BaselineError as exc:
        refusal = str(exc)
    if refusal is not None:  # outside the except block, so no exception context is attached
        raise WriteRefused(refusal)
