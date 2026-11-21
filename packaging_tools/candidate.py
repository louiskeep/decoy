"""Write the release candidate record beside a signed bundle set (REL-GATE design note 6).

`SHA256SUMS` lists every tarball, signature, installer and the version document in the dist
directory, sorted by name, in `sha256sum` format. `candidate.json` names the release (CLI
version and commit, engine tag and commit) and holds the SHA-256 of `SHA256SUMS`, so a smoke
summary and the readiness instance can be tied to exactly these bytes.

    python -m packaging_tools.candidate --dist DIR --cli-version 1.0.0 --cli-sha SHA \\
        --engine-tag v0.28.2 --engine-commit SHA

`read_candidate` is the one strict reader the smoke and `scripts/release/record_smoke.py` use,
and the smoke summary's schema and step names live here so both sides read the same ones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from decoy.distribution.manifest import sha256_file

SCHEMA = "decoy-release-candidate/v1"
SUMS_NAME = "SHA256SUMS"
CANDIDATE_NAME = "candidate.json"
INSTALLERS = ("install.sh", "install.ps1")
VERSION_DOCUMENT = "version.json"
# The smoke summary `smoke_install.py --from-dist` prints and `record_smoke.py` reads (6.4).
SUMMARY_SCHEMA = "decoy-release-smoke/v1"
# `cleanup` is last and set after the run: it passes only when the temp root (and the mask
# secret in it) is gone, so a run that left it can never be recorded as green.
SMOKE_STEPS = ("candidate", "version_document", "installer_key", "install", "bundle_key",
               "version", "doctor", "native", "template", "cleanup")  # fmt: skip
# Targets the smoke refuses and the log never takes this cycle, with the reason (5.4, Q5).
GATED_TARGETS = {
    "windows-x86_64": "Windows is gated off this cycle (decoy.distribution.targets) and "
    "install.ps1 has no local-bundle input; REL-GATE Q5 decides when it is smoked",
}
FIELDS = ("cli_version", "cli_sha", "engine_tag", "engine_commit", "sha256sums_sha256")
_PATTERNS = {
    "cli_version": re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"),
    "cli_sha": re.compile(r"[0-9a-f]{40}"),
    "engine_tag": re.compile(r"v\d+\.\d+\.\d+"),
    "engine_commit": re.compile(r"[0-9a-f]{40}"),
    "sha256sums_sha256": re.compile(r"[0-9a-f]{64}"),
}
_SUMS_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)")


def listed(name: str) -> bool:
    return name.endswith((".tar.gz", ".sig")) or name in INSTALLERS or name == VERSION_DOCUMENT


def sums_text(dist: Path) -> str:
    names = sorted(p.name for p in dist.iterdir() if p.is_file() and listed(p.name))
    if not any(n.endswith(".tar.gz") for n in names) or VERSION_DOCUMENT not in names:
        raise ValueError("candidate_set_incomplete")
    return "".join(f"{sha256_file(dist / name)}  {name}\n" for name in names)


def parse_sums(text: str) -> dict[str, str]:
    """Name to digest; a malformed line, a path or a repeated name is refused."""
    listing: dict[str, str] = {}
    for line in text.splitlines():
        match = _SUMS_LINE.fullmatch(line)
        if match is None or match.group(2) in listing:
            raise ValueError("sha256sums_malformed")
        listing[match.group(2)] = match.group(1)
    if not text.endswith("\n") or not listing:
        raise ValueError("sha256sums_malformed")
    return listing


def strict_json(data: bytes) -> Any:
    """JSON with duplicate keys refused, so two readers cannot see different values."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_key")
        return dict(items)

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs)


def check_candidate(record: Any) -> dict[str, str]:
    if not isinstance(record, dict) or set(record) != {"schema", *FIELDS}:
        raise ValueError("candidate_fields")
    if record["schema"] != SCHEMA:
        raise ValueError("candidate_schema")
    for field in FIELDS:
        value = record[field]
        if type(value) is not str or not _PATTERNS[field].fullmatch(value):
            raise ValueError("candidate_field_type")
    return record


def read_candidate(path: Path) -> dict[str, str]:
    return check_candidate(strict_json(path.read_bytes()))


def write(
    dist: Path, *, cli_version: str, cli_sha: str, engine_tag: str, engine_commit: str
) -> dict[str, str]:
    text = sums_text(dist)
    record = check_candidate(
        {
            "schema": SCHEMA,
            "cli_version": cli_version,
            "cli_sha": cli_sha,
            "engine_tag": engine_tag,
            "engine_commit": engine_commit,
            "sha256sums_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    )
    (dist / SUMS_NAME).write_text(text, encoding="utf-8")
    (dist / CANDIDATE_NAME).write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="candidate", description=__doc__.splitlines()[0])
    ap.add_argument("--dist", required=True, type=Path, help="the signed bundle set")
    for field in ("cli-version", "cli-sha", "engine-tag", "engine-commit"):
        ap.add_argument(f"--{field}", required=True)
    args = ap.parse_args(argv)
    try:
        write(
            args.dist,
            cli_version=args.cli_version,
            cli_sha=args.cli_sha,
            engine_tag=args.engine_tag,
            engine_commit=args.engine_commit,
        )
    except ValueError as exc:
        print(f"candidate: {exc}", file=sys.stderr)
        return 1
    print(f"candidate: wrote {SUMS_NAME} and {CANDIDATE_NAME}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
