"""One walker over the live Click command tree, shared by the surface sentries.

``commands()`` and ``options()`` are the one parameter-aware traversal: every command (the root
included, path ``()``) with its Click object and inherited hidden flag, and every option or argument
with each spelling. Every other walker below is built on them, so a fix to root handling, hidden
ancestry or aliases lands once. ``walk()`` returns every command path with its kind and hidden flag, read from the real
``decoy.__main__.app``. ``visible_paths()`` drops hidden commands (and anything under a hidden
group); ``registry()`` is the two-level view the docs-consistency sentry uses, hidden included;
``json_leaf_commands()`` names the visible leaf commands that take ``--json``.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import typer.main

from decoy.__main__ import app


class Node(NamedTuple):
    path: tuple[str, ...]
    is_group: bool
    hidden: bool  # the command itself, or any group above it, is hidden


class Cmd(NamedTuple):
    path: tuple[str, ...]  # () is the root
    command: Any  # the live Click command
    is_group: bool
    hidden: bool  # the command itself, or any group above it, is hidden


class Opt(NamedTuple):
    cmd: Cmd
    param: Any  # the live Click parameter
    spellings: tuple[str, ...]  # every flag spelling; the parameter name for an argument
    hidden: bool  # the parameter itself is hidden (see cmd.hidden for the command)


def commands(root: Any = None) -> list[Cmd]:
    """Every command in the tree, root first, parents before children. A command registered
    under two names appears once per path."""
    found: list[Cmd] = []

    def visit(cmd: Any, path: tuple[str, ...], hidden_above: bool) -> None:
        hidden = hidden_above or bool(getattr(cmd, "hidden", False))
        found.append(Cmd(path, cmd, bool(getattr(cmd, "commands", None)), hidden))
        for name, sub in getattr(cmd, "commands", {}).items():
            visit(sub, (*path, name), hidden)

    visit(typer.main.get_command(app) if root is None else root, (), False)
    return found


def options(root: Any = None) -> list[Opt]:
    """Every parameter of every command, root and group parameters included."""
    return [
        Opt(
            c,
            p,
            tuple(getattr(p, "opts", None) or ()) + tuple(getattr(p, "secondary_opts", None) or ())
            or (str(p.name),),
            bool(getattr(p, "hidden", False)),
        )
        for c in commands(root)
        for p in getattr(c.command, "params", ())
    ]


def walk() -> list[Node]:
    return [Node(c.path, c.is_group, c.hidden) for c in commands() if c.path]


def visible_paths() -> set[tuple[str, ...]]:
    return {n.path for n in walk() if not n.hidden}


def registry() -> tuple[set[str], dict[str, set[str]]]:
    """(top-level leaf command names, {group name: {its leaf subcommand names}}), hidden included."""
    nodes = walk()
    leaf_top = {n.path[0] for n in nodes if len(n.path) == 1 and not n.is_group}
    groups: dict[str, set[str]] = {
        n.path[0]: set() for n in nodes if len(n.path) == 1 and n.is_group
    }
    for n in nodes:
        if len(n.path) == 2 and not n.is_group and n.path[0] in groups:
            groups[n.path[0]].add(n.path[1])
    return leaf_top, groups


def json_leaf_commands() -> set[str]:
    """Space-joined paths of the visible leaf commands that take ``--json``."""
    return {
        " ".join(o.cmd.path)
        for o in options()
        if o.cmd.path and not o.cmd.hidden and not o.cmd.is_group and "--json" in o.spellings
    }
