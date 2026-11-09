"""One walker over the live Click command tree, shared by the surface sentries.

``walk()`` returns every command path with its kind and hidden flag, read from the real
``decoy.__main__.app``. ``visible_paths()`` drops hidden commands (and anything under a hidden
group); ``registry()`` is the two-level view the docs-consistency sentry uses, hidden included.
"""

from __future__ import annotations

from typing import NamedTuple

import typer.main

from decoy.__main__ import app


class Node(NamedTuple):
    path: tuple[str, ...]
    is_group: bool
    hidden: bool  # the command itself, or any group above it, is hidden


def walk() -> list[Node]:
    nodes: list[Node] = []

    def visit(cmd: object, prefix: tuple[str, ...], hidden_above: bool) -> None:
        for name, sub in getattr(cmd, "commands", {}).items():
            hidden = hidden_above or bool(getattr(sub, "hidden", False))
            is_group = bool(getattr(sub, "commands", None))
            nodes.append(Node((*prefix, name), is_group, hidden))
            visit(sub, (*prefix, name), hidden)

    visit(typer.main.get_command(app), (), False)
    return nodes


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
