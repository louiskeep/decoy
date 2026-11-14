"""G-ONE-ENV-FLAG: the CLI reads environment switches only through `decoy._env_flags`.

Two spellings of one switch drift: `CI=false` once counted as CI and `NO_COLOR=` (empty) once
turned colour off, each because a site tested truthiness or `is not None` itself. Every read of
`os.environ` or `os.getenv` under `src/decoy` is a site, keyed `(path, function, variable)`.
`_env_flags.py` is the one reader of switches. The sites below read a path, a URL, a secret or
a number, not a switch, and each says why; an entry that no longer matches a real read fails,
so the list cannot hold dead rows.

A read is reported through a bound import (`os.environ.get`, `os.getenv`, `os.environ[...]`,
`from os import environ as e; e.get(...)`), by `tests/sentry/io_policy/_calls.py`. Named limits:
a copy made earlier (`env = os.environ; env.get(...)`), `dict(os.environ)`, `k in os.environ`
and `os.environ` handed to another function are not reads this scan sees.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tests.sentry.io_policy import _calls

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OWNER = "_env_flags.py"
DYNAMIC = "<dynamic>"

_GETTERS = {"os.environ.get", "os.getenv"}


@dataclass(frozen=True)
class AllowedRead:
    path: str
    function: str
    variable: str
    reason: str


ALLOWLIST: tuple[AllowedRead, ...] = (
    AllowedRead("_update_check.py", "check_latest", "DECOY_VERSION_URL", "a URL, not a switch"),
    AllowedRead(
        "distribution/release_key.py", "pinned_public_pem", "DECOY_RELEASE_PUBKEY_FILE", "a path"
    ),
    AllowedRead("distribution/layout.py", "managed_home", "DECOY_HOME", "a path"),
    AllowedRead("distribution/layout.py", "bin_dir", "DECOY_BIN_DIR", "a path"),
    AllowedRead("cli/io/_pipelines.py", "_env_project", "DECOY_PROJECT", "a path"),
    AllowedRead("ci/_git.py", "git_env", DYNAMIC, "copies a fixed list of names into a child env"),
    AllowedRead("cli/run/_notify.py", "_otel_endpoint", "DECOY_OTEL_ENDPOINT", "a URL"),
    AllowedRead("cli/run/_notify.py", "_otel_headers", "DECOY_OTEL_HEADERS", "a header secret"),
    AllowedRead(
        "cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_WEBHOOK_SECRET", "a signing secret"
    ),
    AllowedRead("cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_SMTP_HOST", "a host name"),
    AllowedRead("cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_SMTP_PORT", "a number"),
    AllowedRead("cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_SMTP_USER", "a user name"),
    AllowedRead("cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_SMTP_PASS", "a secret"),
    AllowedRead("cli/run/_notify.py", "_smtp_target", "DECOY_NOTIFY_SMTP_FROM", "an address"),
)


def _first_arg(call: ast.Call | None) -> str:
    if call is not None and call.args:
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return DYNAMIC


def reads_in_source(source: str, rel: str) -> set[tuple[str, str, str]]:
    """`(path, function, variable)` for every environment read in one file."""
    found: set[tuple[str, str, str]] = set()
    for s in _calls.sites(ast.parse(source)):
        if not isinstance(s.node, (ast.Name, ast.Attribute)):
            continue
        parent = s.ancestors[-1][0] if s.ancestors else None
        name = s.name
        if name in _GETTERS:
            call = parent if isinstance(parent, ast.Call) and parent.func is s.node else None
            found.add((rel, s.scope, _first_arg(call)))
        elif name == "os.environ" and isinstance(parent, ast.Subscript) and parent.value is s.node:
            key = parent.slice
            literal = isinstance(key, ast.Constant) and isinstance(key.value, str)
            found.add((rel, s.scope, key.value if literal else DYNAMIC))  # type: ignore[union-attr]
    return found


def reads(files: dict[str, str]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for rel, source in files.items():
        if rel != OWNER:
            out |= reads_in_source(source, rel)
    return out


def problems(
    files: dict[str, str], allow: tuple[AllowedRead, ...] = ALLOWLIST
) -> tuple[list[str], list[str]]:
    """`(unlisted reads, allowlist entries with no matching read)`, as readable lines."""
    found = reads(files)
    listed = {(a.path, a.function, a.variable) for a in allow}
    unlisted = [f"{p}::{f} reads {v}" for p, f, v in sorted(found - listed)]
    stale = [f"{p}::{f} {v}" for p, f, v in sorted(listed - found)]
    return unlisted, stale


def _src_files() -> dict[str, str]:
    return {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(SRC.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


def test_every_environment_read_is_the_flag_module_or_a_listed_non_switch() -> None:
    unlisted, stale = problems(_src_files())
    assert unlisted == [], "read a switch through decoy._env_flags, or list a non-switch read"
    assert stale == [], "allowlist rows with no matching read (remove them)"


def test_the_flag_module_exists_and_reads_the_environment() -> None:
    files = _src_files()
    assert OWNER in files
    assert reads_in_source(files[OWNER], OWNER), "the owner no longer reads the environment"


def test_every_allowlisted_read_has_a_reason() -> None:
    assert all(len(a.reason) >= 5 for a in ALLOWLIST)
    assert len({(a.path, a.function, a.variable) for a in ALLOWLIST}) == len(ALLOWLIST)


# --- seeded spellings: each turns the scan red --------------------------------------------

_SEEDS = {
    "equals": 'import os\ndef f():\n    return os.environ.get("X") == "1"\n',
    "getenv": 'import os\ndef f():\n    return os.getenv("X", "0") in {"1"}\n',
    "subscript": 'import os\ndef f():\n    return os.environ["X"].strip().lower() == "true"\n',
    "aliased": 'from os import environ as e\ndef f():\n    return e.get("X") != "0"\n',
    "from_getenv": 'from os import getenv as g\ndef f():\n    return g("X")\n',
    "bool": 'import os\ndef f():\n    return bool(os.environ.get("X"))\n',
    "no_color": 'import os\ndef f():\n    return os.environ.get("NO_COLOR") is not None\n',
    "ci": 'import os\ndef f():\n    if os.environ.get("CI"):\n        return 1\n',
    "dynamic": "import os\ndef f(n):\n    return os.environ.get(n)\n",
}


def test_each_seeded_spelling_is_seen() -> None:
    for name, source in _SEEDS.items():
        unlisted, _ = problems({f"{name}.py": source}, allow=())
        assert len(unlisted) == 1, f"{name}: {unlisted}"


def test_the_owner_module_and_non_reads_are_allowed() -> None:
    files = {
        OWNER: _SEEDS["equals"],
        "a.py": 'import os\ndef f():\n    return "X" in os.environ and dict(os.environ)\n',
    }
    assert problems(files, allow=()) == ([], [])


def test_a_stale_allowlist_row_is_reported() -> None:
    row = AllowedRead("gone.py", "f", "X", "no longer read")
    assert problems({}, allow=(row,)) == ([], ["gone.py::f X"])
