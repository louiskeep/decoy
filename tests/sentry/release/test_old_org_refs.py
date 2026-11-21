"""AT-O1: the old GitHub org name appears only in the listed files, at most as often as listed.

The scan reads every file git tracks (plus untracked, not-ignored files, so uncommitted work is
seen) and counts case-insensitive hits of the old org name. The result must equal
`tests/sentry/baselines/old-org-refs.json`: a path with hits that is not listed fails, a count
that differs from the live count in either direction fails, and a listed path with no hits fails.
The baseline is a shrink-only ratchet: `scripts/dev/ratchet_check.py` blocks an added key or a
raised `count`. Findings name paths and counts only, never the matched text.

The name is spelled in two pieces so this file does not hold it.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

from tests.sentry._ratchet import load_allowlist

ROOT = Path(__file__).resolve().parents[3]
OLD_ORG = "louis" + "keep"
_PATTERN = re.compile(OLD_ORG, re.IGNORECASE)


def tracked_files(root: Path = ROOT) -> dict[str, bytes]:
    names = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    files: dict[str, bytes] = {}
    for raw in names:
        if raw and (root / raw.decode()).is_file():
            files[raw.decode()] = (root / raw.decode()).read_bytes()
    return files


def live_counts(files: Mapping[str, bytes]) -> dict[str, int]:
    out: dict[str, int] = {}
    for path, data in files.items():
        hits = len(_PATTERN.findall(data.decode("utf-8", errors="ignore")))
        if hits:
            out[path] = hits
    return out


def findings(live: Mapping[str, int], allowed: Mapping[str, Mapping[str, object]]) -> list[str]:
    out: list[str] = []
    for path, hits in sorted(live.items()):
        if path not in allowed:
            out.append(f"{path}: {hits} old-org hit(s) in a file that is not in the allowlist")
        elif allowed[path].get("count") != hits:
            out.append(f"{path}: live count {hits} differs from the allowlist count")
    for path in sorted(set(allowed) - set(live)):
        out.append(f"{path}: allowlisted but has no old-org hit; delete the entry")
    return out


def test_old_org_refs_equal_the_allowlist():
    assert findings(live_counts(tracked_files()), load_allowlist("old-org-refs")) == []


def test_changelog_is_not_allowlisted():
    assert "CHANGELOG.md" not in load_allowlist("old-org-refs")


def test_every_entry_has_a_reason_and_a_positive_count():
    for path, entry in load_allowlist("old-org-refs").items():
        assert isinstance(entry.get("reason"), str) and len(entry["reason"]) >= 15, path
        assert isinstance(entry.get("count"), int) and entry["count"] > 0, path


def test_a_seeded_new_file_with_one_hit_fails():
    allowed = {"a.md": {"count": 1, "reason": "dated record kept as written"}}
    live = live_counts({"a.md": f"x {OLD_ORG}".encode(), "new.md": f"{OLD_ORG.upper()}/r".encode()})
    assert findings(live, allowed) == [
        "new.md: 1 old-org hit(s) in a file that is not in the allowlist"
    ]


def test_a_seeded_extra_hit_in_an_allowlisted_file_fails():
    allowed = {"a.md": {"count": 1, "reason": "dated record kept as written"}}
    live = live_counts({"a.md": f"{OLD_ORG}\n{OLD_ORG}".encode()})
    assert findings(live, allowed) == ["a.md: live count 2 differs from the allowlist count"]


def test_a_fixed_file_must_leave_the_allowlist():
    allowed = {"a.md": {"count": 1, "reason": "dated record kept as written"}}
    assert findings({}, allowed) == ["a.md: allowlisted but has no old-org hit; delete the entry"]


def test_findings_carry_no_matched_text():
    live = live_counts({"n.md": f"secret-{OLD_ORG}-repo".encode()})
    assert all("secret" not in f for f in findings(live, {}))
