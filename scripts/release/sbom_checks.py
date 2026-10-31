"""Fail-closed checks for sbom.sh, run with ``python -I`` in the SBOM tool environment.

Modes (each exits 1 with a registered, basename-free message on refusal):

``pins-with-comments FILE``  the tool requirements file, checked with the bare tool
    interpreter before anything is installed: hashed pins and whole-line comments only.
``runtime FILE``  the runtime pin list: the same grammar with hashes optional, then every
    pin is re-parsed with ``packaging.requirements.Requirement`` (the parser
    ``cyclonedx-py`` relies on), and the list must be non-empty, one pin per PEP 503 name,
    and not the dev-profile lock.
``project PYPROJECT``  ``[project]`` must carry a string ``name`` and ``version``.
``complete FILE SBOM``  the SBOM's components equal the pins as a multiset of
    (PEP 503 name, PEP 440 normalized version), and the root component is present: a pin
    the tool dropped, merged or invented is a hard failure.

The grammar is a strict subset of what pip and ``pip-requirements-parser`` accept, so the
checker and the tool never disagree about where a line starts or what it says: the file is
printable ASCII plus ``\\n`` (``str.splitlines()`` also splits on ``\\r``, ``\\x0b``,
``\\x0c``, ``\\x1c``-``\\x1e``, ``\\x85``, ``\\u2028`` and ``\\u2029``), and versions are
canonical PEP 440 (regex from PEP 440, Appendix B). Whatever still parses differently,
such as a ``# coding:`` declaration the tool honours, is caught by ``complete``.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter

# PEP 440 Appendix B, canonical public version, plus a canonical (lowercase, dot) local part.
_VERSION = (
    r"(?:[1-9][0-9]*!)?(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*"
    r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?(?:\.post(?:0|[1-9][0-9]*))?(?:\.dev(?:0|[1-9][0-9]*))?"
    r"(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?"
)
_PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    rf"==(?P<version>{_VERSION})"
    r"(?: ; [A-Za-z0-9 _.'\"()<>=!~*,+-]+)?"
    r"(?P<cont> \\)?$"
)
_HASH = re.compile(r"^    --hash=sha256:[0-9a-f]{64}(?P<cont> \\)?$")
_COMMENT = re.compile(r"^ *#")
_PRINTABLE = re.compile(r"^[\x20-\x7e]*$")
# lock.sh's --custom-compile-command header: present in every requirements-dev.lock it writes.
_DEV_LOCK_HEADER = "#    scripts/dev/lock.sh"

GRAMMAR = (
    "non-public source or unsupported requirement in the pin list "
    "(SBOM covers well-formed public-index pins only)"
)
TOOL_GRAMMAR = "tool environment install failed: sbom-tool-requirements.txt is not hashed pins only"


def canonical_name(name: str) -> str:
    """PEP 503 normalized project name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def pin_violations(text: str, *, require_hashes: bool, allow_comments: bool = False) -> list[int]:
    """1-based numbers of the lines that break the grammar (empty list = well formed).

    Any character outside printable ASCII is a violation, so ``\\r`` (and CRLF) is refused
    here exactly as on the script path, which reads the raw bytes. A pin ending in a
    backslash must be followed by sha256 lines, each but the last also ending in a
    backslash; a hash line anywhere else is an orphan. With ``require_hashes`` every pin
    must carry at least one hash.
    """
    bad: list[int] = []
    in_continuation = False
    lines = _lines(text)
    for n, line in enumerate(lines, 1):
        if not _PRINTABLE.match(line):
            bad.append(n)
            in_continuation = False
            continue
        if in_continuation:
            m = _HASH.match(line)
            if not m:
                bad.append(n)
            in_continuation = bool(m and m.group("cont"))
            continue
        if line.strip(" ") == "":
            continue
        if allow_comments and _COMMENT.match(line) and not line.endswith("\\"):
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


def pins(text: str) -> list[tuple[str, str, str]]:
    """(name, version, requirement text) per pin line of a well-formed file."""
    out = []
    for line in _lines(text):
        m = _PIN.match(line)
        if m:
            req = line[: -len(m.group("cont"))] if m.group("cont") else line
            out.append((m.group("name"), m.group("version"), req))
    return out


def requirement_violations(text: str) -> list[str]:
    """Pins that ``packaging`` does not read as exactly ``name==version [; marker]``."""
    from packaging.requirements import InvalidRequirement, Requirement

    bad = []
    for name, version, line in pins(text):
        try:
            req = Requirement(line)
        except InvalidRequirement:
            bad.append(line)
            continue
        spec = list(req.specifier)
        if (
            req.name != name
            or req.url
            or req.extras
            or len(spec) != 1
            or spec[0].operator != "=="
            or spec[0].version != version
        ):
            bad.append(line)
    return bad


def _key(name: str, version: str | None) -> tuple[str, object]:
    from packaging.version import InvalidVersion, Version

    try:
        return canonical_name(name), Version(version or "")
    except InvalidVersion:
        return canonical_name(name), f"<unparsed {version!r}>"


def completeness_violations(text: str, sbom: dict) -> list[str]:
    want = Counter(_key(n, v) for n, v, _ in pins(text))
    have = Counter(_key(c.get("name", ""), c.get("version")) for c in sbom.get("components", []))
    diff = [f"{n} {v}" for n, v in sorted({*(want - have), *(have - want)}, key=str)]
    if not (sbom.get("metadata", {}).get("component") or {}).get("name"):
        diff.append("<root component>")
    return diff


def _read(path: str) -> str | None:
    # Raw bytes: text mode would translate CRLF and lone CR before the check sees them.
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        return data.decode("ascii")
    except UnicodeDecodeError:
        return None


def _refuse(message: str) -> int:
    print(f"sbom.sh: {message}", file=sys.stderr)
    return 1


def _runtime(text: str | None) -> int:
    if text is None or pin_violations(text, require_hashes=False, allow_comments=True):
        return _refuse(GRAMMAR)
    if requirement_violations(text):
        return _refuse(GRAMMAR)
    if _DEV_LOCK_HEADER in _lines(text):
        return _refuse("requirements-dev.lock is the dev profile, not a runtime pin list")
    names = [canonical_name(n) for n, _, _ in pins(text)]
    if not names:
        return _refuse("no pins in the pin list")
    if len(set(names)) != len(names):
        return _refuse("duplicate or multi-version pin in the pin list (one pin per package)")
    return 0


def _project(path: str) -> int:
    import tomllib

    try:
        with open(path, "rb") as fh:
            project = tomllib.load(fh).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        project = {}
    if not all(isinstance(project.get(k), str) and project[k] for k in ("name", "version")):
        return _refuse("project metadata missing: pyproject.toml needs [project] name and version")
    return 0


def main(argv: list[str]) -> int:
    mode, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    arity = {"pins-with-comments": 1, "runtime": 1, "project": 1, "complete": 2}
    if arity.get(mode) != len(args):
        print(
            "usage: sbom_checks.py pins-with-comments|runtime|project FILE | complete PINS SBOM",
            file=sys.stderr,
        )
        return 2
    if mode == "project":
        return _project(args[0])
    text = _read(args[0])
    if mode == "pins-with-comments":
        if text is None or pin_violations(text, require_hashes=True, allow_comments=True):
            return _refuse(TOOL_GRAMMAR)
        return 0
    if mode == "runtime":
        return _runtime(text)
    with open(args[1], encoding="utf-8") as fh:
        sbom = json.load(fh)
    if text is None or completeness_violations(text, sbom):
        return _refuse("SBOM does not match the pin list (a pin was dropped, merged or added)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
