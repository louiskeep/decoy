"""G-ONE-CANONICAL: the canonical JSON form lives in the engine (`decoy_engine.records`).

`evidence.compute_manifest_hash` and every record id hash `records.canonical_bytes`. A second
sorted-key `json.dumps` in the CLI is how two "canonical" forms drift apart (one adds
`ensure_ascii=True`, and a hash stops matching). This walks every module under `src/decoy/` for
a `json.dumps` or `json.dump` call (through `import json`, `import json as j` and
`from json import dumps`) whose `sort_keys` keyword is not the constant False. A site fails
unless its file is in ALLOWLIST with the exact recorded site count.

The rule is `sort_keys`, not "sort_keys plus compact separators": a sorted pretty form
(`ci/manifest.py`) or a sorted comparison key (`cli/report.py`) is still a second canonical form,
and the re-FRAME (docs/records/lib-reframe-2026-11-11.md) measured both. Size 5 at L1b.2; the
plan's three (`signing`, `notify`, `installer`) plus those two. Shrink-only ratchet:
tests/sentry/baselines/canonical-json-allow.json.

Named limits: a call through a runtime-bound name or an assignment alias, `**kwargs` that carry
`sort_keys`, and other JSON libraries are not seen.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "canonical-json-allow.json"
_CALLS = frozenset({"dumps", "dump"})


@dataclass(frozen=True)
class AllowedCanonical:
    file: str  # relative to src/decoy
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedCanonical, ...] = (
    AllowedCanonical(
        "distribution/signing.py",
        1,
        "Frozen release-signature input shared with openssl and the build host; rewiring it "
        "would tie release verification to an engine version (plan 3.1).",
    ),
    AllowedCanonical(
        "notify.py",
        1,
        "Webhook body signed with HMAC; different bytes on the wire by design (ASCII-escaped, "
        "platform webhook contract), not a content hash (plan 3.1).",
    ),
    AllowedCanonical(
        "distribution/installer.py",
        1,
        "Trust-state file that install.sh reads with a shell pattern; part of the install "
        "contract, not a content hash (plan 3.1).",
    ),
    AllowedCanonical(
        "ci/manifest.py",
        1,
        "Pretty-printed committed JSON Schema (indent=2) drift-tested against its file; a "
        "stable display form, never hashed.",
    ),
    AllowedCanonical(
        "cli/report.py",
        1,
        "Set-diff key for evidence warnings in report diff; compared in memory only, never "
        "stored or hashed. Move to records.canonical_bytes when report.py is next split.",
    ),
)


def _json_names(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """({local name bound to the json module}, {local name: json member})."""
    modules: set[str] = set()
    members: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name == "json"}
        elif isinstance(node, ast.ImportFrom) and node.module == "json":
            members |= {a.asname or a.name: a.name for a in node.names}
    return modules, members


def _sorted(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "sort_keys":
            return not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
    return False


def canonical_sites(source: str) -> list[int]:
    """Lines of each sorted-key `json.dumps` / `json.dump` call in `source`."""
    tree = ast.parse(source)
    modules, members = _json_names(tree)
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _sorted(node):
            continue
        func = node.func
        if isinstance(func, ast.Name) and members.get(func.id) in _CALLS:
            found.append(node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in _CALLS
            and isinstance(func.value, ast.Name)
            and func.value.id in modules
        ):
            found.append(node.lineno)
    return found


def scan(root: Path) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        sites = canonical_sites(path.read_text(encoding="utf-8"))
        if sites:
            out[path.relative_to(root).as_posix()] = sites
    return out


def findings(
    found: dict[str, list[int]], allow: tuple[AllowedCanonical, ...] = ALLOWLIST
) -> list[str]:
    allowed = {e.file: e.sites for e in allow}
    out = []
    for rel, lines in sorted(found.items()):
        where = ", ".join(map(str, lines))
        if rel not in allowed:
            out.append(
                f"{rel}: canonical json.dumps at line(s) {where}; use records.canonical_bytes"
            )
        elif len(lines) != allowed[rel]:
            out.append(f"{rel}: {len(lines)} site(s), allowlist records {allowed[rel]} ({where})")
    out += [
        f"{rel}: allowlisted but has no canonical site (remove the entry)"
        for rel in sorted(set(allowed) - set(found))
    ]
    return out


def test_no_canonical_json_outside_the_engine_form() -> None:
    assert findings(scan(SRC)) == []


def test_the_evidence_hash_has_no_copy_of_its_own() -> None:
    assert "cli/evidence.py" not in scan(SRC)
    assert "canonical_bytes" in (SRC / "cli" / "evidence.py").read_text(encoding="utf-8")


def test_allowlist_is_five_with_reasons() -> None:
    assert len(ALLOWLIST) == 5
    assert len({e.file for e in ALLOWLIST}) == 5
    assert all(len(e.reason.strip()) >= 15 and e.sites > 0 for e in ALLOWLIST)


def test_baseline_json_records_the_same_sites_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert {k: (v["sites"], v["reason"]) for k, v in entries.items()} == {
        e.file: (e.sites, e.reason) for e in ALLOWLIST
    }


def test_seeded_copy_in_the_library_store_is_red(tmp_path: Path) -> None:
    """M-CANON-COPY: the store hashing its own `json.dumps` is reported."""
    store = tmp_path / "cli" / "library" / "_store.py"
    store.parent.mkdir(parents=True)
    store.write_text(
        "import hashlib, json\n"
        "def rid(d):\n"
        "    raw = json.dumps(d, sort_keys=True, separators=(',', ':'))\n"
        "    return hashlib.sha256(raw.encode()).hexdigest()\n",
        encoding="utf-8",
    )
    assert findings(scan(tmp_path), ()) == [
        "cli/library/_store.py: canonical json.dumps at line(s) 3; use records.canonical_bytes"
    ]


def test_seeded_second_site_in_an_allowlisted_file_is_red() -> None:
    real = scan(SRC)
    seeded = {**real, "notify.py": [*real["notify.py"], 999]}
    assert findings(seeded) == [
        f"notify.py: 2 site(s), allowlist records 1 ({', '.join(map(str, seeded['notify.py']))})"
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import json\njson.dumps(d, sort_keys=True)\n", [2]),
        ("import json as _j\n_j.dumps(d, sort_keys=True, indent=2)\n", [2]),
        ("from json import dumps\ndumps(d, sort_keys=True)\n", [2]),
        ("from json import dumps as d2\nd2(d, sort_keys=flag)\n", [2]),
        ("import json\njson.dump(d, fh, sort_keys=True)\n", [2]),
        ("import json\njson.dumps(d)\n", []),
        ("import json\njson.dumps(d, sort_keys=False)\n", []),
        ("import yaml\nyaml.dump(d, sort_keys=True)\n", []),
        ("import yaml\nyaml.safe_dump(d, sort_keys=False)\n", []),
    ],
)
def test_walk_sees_each_common_form(source: str, expected: list[int]) -> None:
    assert canonical_sites(source) == expected
