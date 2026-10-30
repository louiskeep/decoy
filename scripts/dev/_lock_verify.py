"""Compare the running interpreter's installed distributions with a pinned lock.

Usage: python _lock_verify.py LOCK ALLOWED_EXTRAS KEY_DEP...

LOCK is a `uv pip compile --generate-hashes` file: `name==version` lines, or
`name @ git+URL@COMMIT` for a VCS pin (matched against PEP 610 direct_url.json).
ALLOWED_EXTRAS is a comma list of distributions bootstrap installs outside the
lock (the repo itself, editable). Names compare after PEP 503 normalization.
Prints one row per KEY_DEP and a summary on stdout, and one line per difference
on stderr (bootstrap.sh turns each into a BOOTSTRAP FAIL); exits 1 on any.
Stdlib only, so it runs in any venv."""

from __future__ import annotations

import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?(?:==(\S+)| @ (\S+))")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked(lock: Path) -> dict[str, str]:
    pins = {}
    for line in lock.read_text().splitlines():
        m = _PIN.match(line)
        if m:
            pins[_norm(m.group(1))] = m.group(2) or m.group(3).rstrip("\\").strip()
    return pins


def _installed() -> dict[str, str]:
    have = {}
    for dist in md.distributions():
        version = dist.version
        direct = dist.read_text("direct_url.json")
        if direct:
            info = json.loads(direct)
            if "vcs_info" in info:
                version = f"git+{info['url']}@{info['vcs_info'].get('commit_id', '?')}"
        have[_norm(dist.metadata["Name"])] = version
    return have


def main(lock: Path, allowed: set[str], key_deps: list[str]) -> int:
    want, have = _locked(lock), _installed()
    for dep in key_deps:
        got, pin = have.get(_norm(dep), "absent"), want.get(_norm(dep), "unlocked")
        mark = "OK" if got == pin else "MISMATCH"
        print(f"{dep:<11} installed {got:<10} lock {pin:<10} {mark}")
    problems = [
        f"{name} installed {have.get(name, 'absent')} but {lock.name} pins {pin}"
        for name, pin in sorted(want.items())
        if have.get(name) != pin
    ]
    problems += [
        f"{name} {version} is installed but not in {lock.name}"
        for name, version in sorted(have.items())
        if name not in want and name not in allowed
    ]
    if problems:
        print(f"full env:   DIFFERS from {lock.name}:")
        for p in problems:
            print(f"            {p}")
            print(p, file=sys.stderr)
        return 1
    print(f"full env:   matches {lock.name} exactly ({len(want)} pins)")
    return 0


if __name__ == "__main__":
    extras = {_norm(n) for n in sys.argv[2].split(",") if n}
    sys.exit(main(Path(sys.argv[1]), extras, sys.argv[3:]))
