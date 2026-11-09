"""The one registry of banned user text.

Two lists, each with its scope:

* `DEAD_STRINGS`: invocation strings of deleted commands. Scope: every line of every
  `src/decoy/**/*.py` file, comments and docstrings included (checked by
  `tests/unit/test_no_dead_command_strings.py`).
* `BANNED_USER_TEXT`: internal names a user must never read (ticket ids, private module
  paths, hidden command names). Scope: text a user can see, namely command help, usage lines,
  `explain` topics, string constants outside docstrings, and bundled templates (checked by
  `tests/sentry/cli_text/test_user_text_internal_names.py`). Comments and docstrings keep their
  ids because no user reads them.

An allowlist entry names the file, the exact string constant and the reason it is not user text.
"""

from __future__ import annotations

import re

DEAD_STRINGS = (
    "storm scan",
    "storm test",
    # S2: top-level commands removed / re-parented. The space is load-bearing:
    # it keeps `decoy validate preflight` and `decoy validate compile` (the
    # live forms) from matching `decoy preflight` / `decoy compile`.
    "decoy compile",
    "decoy plan",
    "decoy preflight",
    # S3a: `profile` + `storm analyze` merged into `decoy scan`; the saved-scan
    # subcommands moved from `storm` to `scan`. `storm integrity` stays live and
    # is NOT listed here.
    "decoy profile",
    "decoy storm analyze",
    "storm fields",
    "storm show",
    "storm diff",
    # S3b: the `strategies`/`providers`/`checksums`/`validators` sub-apps and the
    # `templates` sub-app folded into `decoy list KIND` / `decoy show KIND`. The
    # removed top-level invocation strings are dead. `decoy templates` catches
    # both `templates list` and `templates show`; it does NOT match the live
    # `decoy list templates` / `decoy show template` forms (no "decoy templates"
    # substring in either).
    "decoy strategies",
    "decoy providers",
    "decoy checksums",
    "decoy validators",
    "decoy templates",
    # S4a: the project/catalog/jobs persistence subsystem was deleted and the
    # CLI is now stateless. The trailing space keeps `decoy report ...` (the
    # live post-run surface) from matching; none of these three has a
    # surviving `decoy ...` form.
    "decoy project",
    "decoy catalog",
    "decoy jobs",
    # S4b: the `evidence`, `vault`, and `storm` groups and `validate
    # distribution` folded into `decoy report` (verify+show / vault / integrity
    # / fidelity). The live forms are `decoy report ...`, which none of these
    # substrings match. `storm integrity` and `validate distribution` (the
    # exact nested paths) are dead; `decoy evidence` / `decoy vault` catch
    # every invocation of those removed groups.
    "decoy evidence",
    "decoy vault",
    "storm integrity",
    "validate distribution",
)

BANNED_USER_TEXT = tuple(
    re.compile(p)
    for p in (
        r"OSS\.\d",
        r"FC-\d",
        r"CLI\.\d",
        r"DE-\d",
        r"SP-\d",
        r"\bS\d+-[A-Z]",
        r"storm-reframe",
        r"decoy-platform/",
        r"decoy_engine\.\w+\._",
        r"(?<!\w)_scan\b",
        r"(?<!\w)_gate\b",
    )
)

# (path under src/decoy, substring of the constant) -> reason it is not user text.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("cli/scan.py", "_scan"): (
        "registration name of the hidden default command; the usage path is rewritten to "
        "`decoy scan` by the default-group context, so no user reads the name"
    ),
    ("cli/validate.py", "_gate"): (
        "registration name of the hidden default command; the usage path is rewritten to "
        "`decoy validate` by the default-group context, so no user reads the name"
    ),
}
