"""AT-S2b: every hidden command and option has a tier row in `docs/release/frozen-surfaces.md`.

The sentry walks the real Click tree with `tests.command_tree.walk()` and reads the one map row whose
surface is "Hidden commands and options". Its "Completeness source" cell lists `name: tier` spans.
A command's name is its space-joined path (`scan _scan`); an option's name is the command path then
the flag (`ci check --unsafe-debug-log`). A hidden name with no span fails, a span naming something that
no longer exists fails, and the tier must match the rule: a hidden command whose last segment starts
with `_` is `internal`, every other hidden command or option is `frozen-hidden`.

Seeded mutations (each makes the named test red): add `hidden=True` to any option of `run`
(`test_the_real_map_is_clean`); delete a span from the row (`test_a_dropped_span_is_found`);
rename `_gate` in the map (`test_a_stale_span_is_found`); change a tier (`test_a_wrong_tier_is_found`);
mark every command visible (`test_the_walk_finds_the_known_names`).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.command_tree import Cmd, Opt, commands, options

ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "docs" / "release" / "frozen-surfaces.md"
ROW_SURFACE = "Hidden commands and options"
TIERS = ("internal", "frozen-hidden")
SPAN = re.compile(r"`([^`]+): (internal|frozen-hidden)`")
# The names the plan lists. The walk is the source of truth; this only proves the walk sees them.
KNOWN = {"scan _scan", "validate _gate", "upgrade --url", "ci check --unsafe-debug-log"}


def tier_of(name: str, is_option: bool) -> str:
    last = name.split()[-1]
    return "internal" if not is_option and last.startswith("_") else "frozen-hidden"


def hidden_pairs(
    cmds: list[Cmd] | None = None, opts: list[Opt] | None = None
) -> list[tuple[str, str]]:
    """Every hidden command path and every spelling of every hidden option, with its rule tier.

    A hidden name can appear twice (a command registered under two names is two paths; a
    spelling shared by two options is a clash), so this stays a list for the caller to judge.
    """
    pairs: list[tuple[str, str]] = []
    for c in commands() if cmds is None else cmds:
        if c.path and c.hidden:
            name = " ".join(c.path)
            pairs.append((name, tier_of(name, False)))
    for o in options() if opts is None else opts:
        if o.hidden and o.spellings:
            for flag in o.spellings:
                key = " ".join((*o.cmd.path, flag))
                pairs.append((key, tier_of(key, True)))
    return pairs


def hidden_names() -> dict[str, str]:
    """The live hidden names with their rule tier; a name that gets two tiers fails here."""
    found: dict[str, str] = {}
    for name, tier in hidden_pairs():
        assert found.setdefault(name, tier) == tier, f"{name} gets two live tiers"
    return found


def map_row(text: str) -> str:
    rows = [ln for ln in text.splitlines() if ln.startswith(f"| {ROW_SURFACE} |")]
    assert len(rows) == 1, f"the map needs exactly one '{ROW_SURFACE}' row, found {len(rows)}"
    return rows[0]


def mapped_pairs(text: str) -> list[tuple[str, str]]:
    cell = map_row(text).strip().strip("|").split("|")[1]
    return SPAN.findall(cell)


def mapped(text: str) -> dict[str, str]:
    return dict(mapped_pairs(text))


def findings(text: str, live: dict[str, str] | None = None) -> list[str]:
    """Why the map's hidden-names row is not true for the live tree; empty when it is."""
    live = hidden_names() if live is None else live
    listed = mapped(text)
    tiers: dict[str, set[str]] = {}
    for name, tier in mapped_pairs(text):
        tiers.setdefault(name, set()).add(tier)
    found = [
        f"contradictory tiers for {n}: {', '.join(sorted(t))}"
        for n, t in sorted(tiers.items())
        if len(t) > 1
    ]
    found += [f"hidden name with no tier row: {n}" for n in sorted(live.keys() - listed.keys())]
    found += [f"tier row for a name that is gone: {n}" for n in sorted(listed.keys() - live.keys())]
    found += [
        f"wrong tier for {n}: map says {listed[n]}, rule says {live[n]}"
        for n in sorted(live.keys() & listed.keys())
        if len(tiers[n]) == 1 and listed[n] != live[n]
    ]
    return found


def test_the_walk_finds_the_known_names() -> None:
    assert KNOWN <= hidden_names().keys()


def test_internal_names_start_with_an_underscore() -> None:
    for name, tier in hidden_names().items():
        assert (tier == "internal") == (name.split()[-1].startswith("_")), name


def test_the_real_map_is_clean() -> None:
    assert findings(MAP.read_text(encoding="utf-8")) == []


def test_the_row_uses_only_known_tiers() -> None:
    cell = map_row(MAP.read_text(encoding="utf-8")).strip().strip("|").split("|")[1]
    assert len(SPAN.findall(cell)) == cell.count("`") // 2


def test_a_dropped_span_is_found() -> None:
    text = MAP.read_text(encoding="utf-8")
    for name in hidden_names():
        seeded = re.sub(rf"`{re.escape(name)}: [a-z-]+`;? ?", "", text, count=1)
        assert any(f.endswith(name) for f in findings(seeded)), name


def test_a_stale_span_is_found() -> None:
    text = MAP.read_text(encoding="utf-8").replace("`validate _gate:", "`validate _gone:", 1)
    got = findings(text)
    assert "tier row for a name that is gone: validate _gone" in got
    assert "hidden name with no tier row: validate _gate" in got


def test_a_wrong_tier_is_found() -> None:
    text = MAP.read_text(encoding="utf-8").replace(
        "`upgrade --url: frozen-hidden`", "`upgrade --url: internal`", 1
    )
    assert any(f.startswith("wrong tier for upgrade --url") for f in findings(text))


def test_a_new_hidden_name_is_found() -> None:
    live = {**hidden_names(), "run --new-secret": "frozen-hidden"}
    assert "hidden name with no tier row: run --new-secret" in findings(
        MAP.read_text(encoding="utf-8"), live
    )


def test_duplicate_spans_with_contradictory_tiers_fail() -> None:
    text = MAP.read_text(encoding="utf-8")
    seeded = text.replace(
        "`upgrade --url: frozen-hidden`",
        "`upgrade --url: frozen-hidden`; `upgrade --url: internal`",
        1,
    )
    assert "contradictory tiers for upgrade --url: frozen-hidden, internal" in findings(seeded)


# Synthetic trees: the walker must see what the real tree may not have yet.
def _synthetic() -> tuple[list[Cmd], list[Opt]]:
    import click

    def cmd(name: str, *, hidden: bool = False, params: tuple = (), subs: dict | None = None):
        if subs is None:
            c: click.Command = click.Command(name, params=list(params), hidden=hidden)
        else:
            c = click.Group(name, params=list(params), hidden=hidden, commands=subs)
        return c

    leaf = cmd("leaf", params=(click.Option(["--deep", "-d"], hidden=True),))
    inner = cmd("inner", subs={"leaf": leaf, "again": leaf})
    root = cmd(
        "root",
        params=(click.Option(["--root-secret", "-r"], hidden=True), click.Option(["--shown"])),
        subs={
            "grp": cmd(
                "grp", params=(click.Option(["--grp-secret"], hidden=True),), subs={"x": cmd("x")}
            ),
            "_sub": cmd("_sub", hidden=True, subs={"nested": inner}),
        },
    )
    return commands(root), options(root)


def test_synthetic_tree_root_group_nested_and_inherited_and_aliases() -> None:
    cmds, opts = _synthetic()
    got = dict(hidden_pairs(cmds, opts))
    assert got["--root-secret"] == "frozen-hidden" and got["-r"] == "frozen-hidden"
    assert got["grp --grp-secret"] == "frozen-hidden"
    assert got["_sub"] == "internal"
    assert got["_sub nested"] == "frozen-hidden"  # hidden by inheritance, no underscore
    assert got["_sub nested leaf"] == "frozen-hidden"
    assert got["_sub nested again"] == "frozen-hidden"  # one command, two paths
    assert got["_sub nested leaf --deep"] == got["_sub nested leaf -d"]
    assert "--shown" not in got and "grp x" not in got and "grp" not in got
