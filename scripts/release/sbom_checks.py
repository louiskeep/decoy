"""Fail-closed input check for sbom.sh (stdlib only, runs in the hashed tool environment).

The pin list must be a well-formed sequence of ``name==version [ ; marker ]`` lines, each
optionally followed by its sha256 hash lines, plus whole-line comments and blank lines, and
nothing else: no options, inline comments, URLs or paths, which would carry infrastructure
text into the SBOM. Hash lines must belong to a pin (no orphans, no dangling continuation).
"""

from __future__ import annotations

import re
import sys

# PEP 440 version characters only; marker text limited to marker grammar characters.
_PIN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
    r"==[A-Za-z0-9.!+_-]+"
    r"(?: ; [A-Za-z0-9 _.'\"()<>=!~*,+-]+)?"
    r"(?P<cont> \\)?$"
)
_HASH = re.compile(r"^    --hash=sha256:[0-9a-f]{64}(?P<cont> \\)?$")


def pin_violations(text: str, *, require_hashes: bool, allow_comments: bool = False) -> list[int]:
    """1-based numbers of the lines that break the grammar (empty list = well formed).

    A pin ending in a backslash must be followed by sha256 lines, each but the last also
    ending in a backslash; a hash line anywhere else is an orphan. With ``require_hashes``
    every pin must carry at least one hash.
    """
    bad: list[int] = []
    in_continuation = False
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for n, line in enumerate(lines, 1):
        if in_continuation:
            m = _HASH.match(line)
            if not m:
                bad.append(n)
            in_continuation = bool(m and m.group("cont"))
            continue
        if line.strip() == "":
            continue
        if allow_comments and re.match(r"^\s*#", line) and not line.endswith("\\"):
            continue
        m = _PIN.match(line)
        if not m or "--" in line:
            bad.append(n)
            continue
        in_continuation = bool(m.group("cont"))
        if require_hashes and not in_continuation:
            bad.append(n)
    if in_continuation:
        bad.append(len(lines))
    return sorted(set(bad))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: sbom_checks.py PINS_FILE", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        text = fh.read()
    if pin_violations(text, require_hashes=False, allow_comments=True):
        print(
            "sbom.sh: non-public source or unsupported requirement in the pin list "
            "(SBOM covers well-formed public-index pins only)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
