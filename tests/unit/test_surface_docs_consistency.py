"""Anti-drift sentry for the two hand-written CLI surfaces.

`docs/cli-reference.md` is already drift-protected by `test_cli_surface.py`
(it re-renders from the Typer app). The gap this file closes is the two
surfaces nobody regenerates: the root-help block (`_ROOT_HELP` in
`src/decoy/__main__.py`) and the README "Common commands" table.

Both are read against the LIVE Typer app (`decoy.__main__.app`), via
`app.registered_commands` / `app.registered_groups`, so this test cannot go
stale: adding, removing, or re-parenting a command and forgetting to update
the help/README fails here.

The extractor resolves NESTED command paths (`storm analyze`, `validate
config`, `report show`) against the registry rather than treating every token
as a flat command -- an example line carries args, flags, and placeholders
after the command path, and a group reference is two tokens, not one.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from decoy.__main__ import _ROOT_HELP, app

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "decoy"
README = REPO_ROOT / "README.md"

# ---------------------------------------------------------------------------
# Deliberate omissions. These are the registered top-level commands that are
# intentionally NOT advertised on a given hand-written surface. Listing them
# makes omission a reviewed choice: a NEW top-level command absent from the
# surface (and from the matching allowlist) is drift and fails the test.
# ---------------------------------------------------------------------------

# Root help is a curated quick-start. These power/introspection commands are
# deliberately kept out of it (full surface is in `decoy --help`).
_ROOT_HELP_OMITTED = frozenset(
    {
        "schema",
        "doctor",
        # S3b: the four registry sub-apps folded into `list`/`show`, which ARE
        # advertised in the root help (`decoy list templates` / `show template`).
        # S4b: `vault`, `evidence`, and `storm` are gone -- their verbs folded
        # into `decoy report` (vault / verify+show / integrity), so they are no
        # longer registered and must not appear here.
    }
)

# The README "Common commands" table is an even shorter first-contact list:
# everything below is a real command that the table deliberately does not
# repeat (the table points readers to `decoy --help` for the rest).
_README_TABLE_OMITTED = frozenset(
    {
        "unmask",
        "fit",
        "info",
        "schema",
        "doctor",
        "subset",
        # S3b: the four registry sub-apps folded into `list`/`show`; the README
        # table advertises `decoy list templates` / `decoy show template`.
        # S4b: `vault`, `evidence`, and `storm` are gone (folded into `decoy
        # report`), so they are no longer registered and must not appear here.
        # `report` is now featured in the table (the post-run surface), so it
        # is no longer allowlisted out.
    }
)


# ---------------------------------------------------------------------------
# Live registry introspection
# ---------------------------------------------------------------------------


def _registry() -> tuple[set[str], dict[str, set[str]]]:
    """Return (top-level leaf command names, {group name: {subcommand names}}).

    Read straight off the Typer app so it tracks the real command tree.
    """
    leaf_top = {c.name for c in app.registered_commands if c.name}
    groups: dict[str, set[str]] = {}
    for g in app.registered_groups:
        if not g.name:
            continue
        ti = g.typer_instance
        groups[g.name] = {c.name for c in ti.registered_commands if c.name}
    return leaf_top, groups


LEAF_TOP, GROUPS = _registry()
TOP_LEVEL = LEAF_TOP | set(GROUPS)
# Full paths that resolve to a runnable command, plus bare group names.
LEAF_PATHS = LEAF_TOP | {f"{g} {sub}" for g, subs in GROUPS.items() for sub in subs}
VALID_TARGETS = LEAF_PATHS | set(GROUPS)

_CMDLIKE = re.compile(r"^[a-z][a-z0-9-]*$")


def _extract_path(after_decoy: str) -> str | None:
    """Resolve the command path from the text following `decoy ` on one line.

    Consume leading command-like tokens (lowercase words), stopping at the
    first flag (`-...`) or arg/placeholder (`<run-id>`, `[file]`, `data.csv`,
    `FOO`). Then resolve against the registry:
      - a top-level leaf command owns exactly one token (the rest are args);
      - a group owns its name plus the next command-like token (its sub).
    A first token that is neither a leaf nor a group is returned as-is so the
    caller's membership assertion flags it as a phantom.
    """
    tokens: list[str] = []
    for tok in after_decoy.split():
        if tok.startswith("-"):
            break
        if not _CMDLIKE.match(tok):
            break
        tokens.append(tok)
    if not tokens:
        return None
    head = tokens[0]
    if head in LEAF_TOP:
        return head
    if head in GROUPS:
        if len(tokens) >= 2:
            return f"{head} {tokens[1]}"
        return head
    # Unknown head: hand it back verbatim so it reads as a phantom.
    return head


def _paths_from_text(text: str) -> list[str]:
    """Every command path named by a `decoy ...` fragment in a block of text."""
    paths: list[str] = []
    for line in text.splitlines():
        idx = line.find("decoy ")
        if idx < 0:
            continue
        path = _extract_path(line[idx + len("decoy ") :])
        if path is not None:
            paths.append(path)
    return paths


def _readme_table_rows() -> list[str]:
    """First-column `decoy ...` cells from the README 'Common commands' table."""
    text = README.read_text(encoding="utf-8")
    lines = text.splitlines()
    rows: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped.lower() == "## common commands"
            continue
        if not in_section:
            continue
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].strip("` ")
        if first.startswith("decoy "):
            rows.append(first)
    return rows


# ---------------------------------------------------------------------------
# Self-check: the extractor must actually reject a fake command.
# ---------------------------------------------------------------------------


def test_extractor_flags_a_phantom() -> None:
    # A made-up command resolves to a path that is NOT in the registry, which
    # is exactly how the assertions below catch drift.
    assert _extract_path("bogus --flag") == "bogus"
    assert "bogus" not in VALID_TARGETS
    # A real nested path resolves and is registered.
    assert _extract_path("report integrity masked.csv") == "report integrity"
    assert "report integrity" in VALID_TARGETS
    # A top-level leaf does not over-consume its positional arg.
    assert _extract_path("explain modes") == "explain"


# ---------------------------------------------------------------------------
# Root help (`_ROOT_HELP`)
# ---------------------------------------------------------------------------


def test_root_help_names_only_registered_commands() -> None:
    offenders = [p for p in _paths_from_text(_ROOT_HELP) if p not in VALID_TARGETS]
    assert not offenders, (
        "_ROOT_HELP in src/decoy/__main__.py names command path(s) that are not "
        f"registered: {sorted(set(offenders))}. Remove the phantom or fix the help."
    )


def test_every_top_level_command_is_in_root_help_or_allowlisted() -> None:
    referenced = {p.split()[0] for p in _paths_from_text(_ROOT_HELP)}
    undocumented = TOP_LEVEL - referenced - _ROOT_HELP_OMITTED
    assert not undocumented, (
        f"Top-level command(s) {sorted(undocumented)} are neither shown in "
        "_ROOT_HELP nor listed in _ROOT_HELP_OMITTED. Add them to the root help "
        "or, if the omission is deliberate, to the allowlist (with a reason)."
    )
    stale = _ROOT_HELP_OMITTED - TOP_LEVEL
    assert not stale, (
        f"_ROOT_HELP_OMITTED lists non-existent command(s) {sorted(stale)}; "
        "prune the allowlist."
    )
    contradiction = _ROOT_HELP_OMITTED & referenced
    assert not contradiction, (
        f"_ROOT_HELP_OMITTED lists command(s) {sorted(contradiction)} that are "
        "actually shown in the root help; remove them from the allowlist."
    )


# ---------------------------------------------------------------------------
# README "Common commands" table
# ---------------------------------------------------------------------------


def test_readme_table_names_only_registered_commands() -> None:
    rows = _readme_table_rows()
    assert rows, "Could not find any `decoy ...` rows in the README 'Common commands' table."
    offenders: list[str] = []
    for cell in rows:
        path = _extract_path(cell[len("decoy ") :])
        if path is None or path not in VALID_TARGETS:
            offenders.append(cell)
    assert not offenders, (
        f"README 'Common commands' table names unregistered command(s): {offenders}."
    )


def test_every_top_level_command_is_in_readme_table_or_allowlisted() -> None:
    rows = _readme_table_rows()
    referenced = set()
    for cell in rows:
        path = _extract_path(cell[len("decoy ") :])
        if path:
            referenced.add(path.split()[0])
    missing = TOP_LEVEL - referenced - _README_TABLE_OMITTED
    assert not missing, (
        f"Top-level command(s) {sorted(missing)} are neither in the README "
        "'Common commands' table nor in _README_TABLE_OMITTED. Add a table row "
        "or, if deliberate, extend the allowlist."
    )
    stale = _README_TABLE_OMITTED - TOP_LEVEL
    assert not stale, (
        f"_README_TABLE_OMITTED lists non-existent command(s) {sorted(stale)}; "
        "prune the allowlist."
    )
    contradiction = _README_TABLE_OMITTED & referenced
    assert not contradiction, (
        f"_README_TABLE_OMITTED lists command(s) {sorted(contradiction)} that are "
        "actually in the table; remove them from the allowlist."
    )


# ---------------------------------------------------------------------------
# Flag-vocabulary grep gate (slice B1): the standalone flag `--out` is gone;
# `--output`/`-o` is the one spelling. `--output` itself must not trip this.
# ---------------------------------------------------------------------------


def test_no_standalone_out_flag_in_source() -> None:
    pattern = re.compile(r"--out(?!put)")
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(SRC_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found the standalone `--out` flag token in source; it was renamed to "
        "`--output`/`-o`:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Default-command handler surface (drift blind spot).
#
# `scan` and `validate` dispatch a bare positional to a hidden handler
# (`_scan`, `_gate`) that `_DefaultCommandGroup.list_commands` keeps out of
# group help, the generated `docs/cli-reference.md`, and so the re-render guard
# in `test_cli_surface.py`. Their flags are therefore the one part of the CLI
# surface no other sentry watches: add, rename, or drop a flag on those
# handlers and nothing else fails. This guard reads the handler's real option
# surface off its callback signature and pins it to a committed map, so a
# change there is forced to be a reviewed edit here (the same mechanism as the
# `_*_OMITTED` allowlists above). Surfacing these options in `--help` and the
# reference is a separate discoverability follow-up, not a drift concern.
# ---------------------------------------------------------------------------


def _handler_surface(callback: object) -> list[str]:
    """The option/arg surface of one command callback, in signature order.

    Each option contributes ALL its spellings joined with `/`
    (`--quiet/-q`), not just the primary one, so renaming or dropping a
    secondary alias is caught. Each positional contributes `<arg:name>`.
    """
    surface: list[str] = []
    for pname, param in inspect.signature(callback).parameters.items():
        param_decls = getattr(param.default, "param_decls", None)
        surface.append("/".join(param_decls) if param_decls else f"<arg:{pname}>")
    return surface


def _default_command_flags() -> dict[str, list[str]]:
    """Return {group name: full option/arg surface of its hidden default handler}."""
    surface: dict[str, list[str]] = {}
    for g in app.registered_groups:
        for c in g.typer_instance.registered_commands:
            if c.name and c.name.startswith("_"):
                surface[g.name] = _handler_surface(c.callback)
    return surface


# The reviewed surface of each default-command handler, every spelling pinned.
# Editing a flag on `_scan`/`_gate` -- including an alias like `-q` or `-o` --
# must update this map in the same diff; that edit IS the drift signal those
# hidden handlers would otherwise escape.
_DEFAULT_COMMAND_FLAGS = {
    "validate": ["<arg:config>", "--json", "--quiet/-q", "--verbose/-v", "--fail-on-warning"],
    "scan": [
        "<arg:source>",
        "--show-fields",
        "--rows",
        "--strategy",
        "--output/-o",
        "--format",
        "--layout",
        "--json",
        "--quiet/-q",
        "--verbose/-v",
    ],
}


def test_default_command_handlers_match_committed_flag_surface() -> None:
    assert _default_command_flags() == _DEFAULT_COMMAND_FLAGS, (
        "A hidden default-command handler (`scan`/`validate`'s `_scan`/`_gate`) "
        "changed its flag/argument surface. These handlers are hidden from help, "
        "the generated reference, and the re-render sentry, so this is the only "
        "guard on them. If the change is intended, update _DEFAULT_COMMAND_FLAGS "
        "to match (every option spelling, aliases included)."
    )


@pytest.mark.parametrize(
    "decls, expected",
    [
        # Primary flag with a short alias: BOTH spellings captured.
        (("--quiet", "-q"), "--quiet/-q"),
        # Renaming the alias changes the captured surface (the gap the first
        # cut of this guard missed -- a primary-only snapshot could not see it).
        (("--quiet", "-s"), "--quiet/-s"),
        # Dropping the alias changes it too.
        (("--quiet",), "--quiet"),
        # Adding an alias changes it.
        (("--json", "-j"), "--json/-j"),
    ],
)
def test_extractor_captures_every_option_spelling(decls, expected) -> None:
    """`_handler_surface` must record ALL of an option's spellings, so the
    committed-surface guard diverges on any alias add/drop/rename. Exercises the
    real extractor against a synthetic callback whose option decls we control."""
    import typer

    def _cb(flag: bool = typer.Option(False, *decls)) -> None: ...

    assert _handler_surface(_cb) == [expected]
