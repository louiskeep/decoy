"""Logical config paths -> physical YAML marks, without guessing.

The pipeline loader is `yaml.safe_load`, which discards source marks. This module makes a
parallel, read-only `yaml.compose` pass over the SAME text and indexes marks under three
path spellings: numeric (`tables.0.columns.2.provider`), semantic (`tables.customers.columns.
email.provider`, from the `name` field of mapping list entries), and plain mapping keys.

A path resolves to a region only when it is exact and unambiguous. A proven parent key yields
a file-level location; wildcards, pseudo-paths, duplicate names or keys, YAML aliases and
merge keys never yield a guessed line. The index stores marks and path tokens only; no
scalar value ever enters it.

Prior art: PyYAML node marks (the same mechanism `yaml.YAMLError.problem_mark` uses) and
the SARIF 2.1.0 region model (one-based lines/columns, exclusive end column, 3.30).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from decoy.ci.contracts import SourceLocation

_AMBIGUOUS = object()
_MERGE_TAG = "tag:yaml.org,2002:merge"
_BRACKET = re.compile(r"\[(\d+)\]")
_MAX_NODES = 200_000


@dataclass(frozen=True)
class _Mark:
    line: int
    column: int
    end_line: int | None
    end_column: int | None


@dataclass
class YamlSourceIndex:
    uri: str
    _marks: dict[str, object] = field(default_factory=dict)

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_bytes(cls, uri: str, data: bytes) -> YamlSourceIndex:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return cls(uri)
        return cls.from_text(uri, text)

    @classmethod
    def from_text(cls, uri: str, text: str) -> YamlSourceIndex:
        index = cls(uri)
        try:
            root = yaml.compose(text, Loader=yaml.SafeLoader)
        except (yaml.YAMLError, ValueError, RecursionError):
            return index
        if root is None:
            return index
        try:
            _Walker(index._marks).walk(root, ())
        except RecursionError:
            index._marks.clear()  # a partial index could hide a duplicate; say nothing instead
        return index

    # -- lookup ---------------------------------------------------------------

    def locate(self, logical_path: str | None) -> SourceLocation | None:
        """Exact region, file-level location for a proven parent, or None."""
        if not logical_path or not isinstance(logical_path, str):
            return None
        normalized = _BRACKET.sub(r".\1", logical_path).strip(".")
        segments = normalized.split(".")
        if any((not s) or s == "*" or s.startswith("<") for s in segments):
            return None
        prefixes = [".".join(segments[:d]) for d in range(1, len(segments) + 1)]
        # Ambiguity anywhere along the path (duplicate key/name) forbids any location.
        if any(self._marks.get(p) is _AMBIGUOUS for p in prefixes):
            return None
        for depth in range(len(prefixes), 0, -1):
            hit = self._marks.get(prefixes[depth - 1])
            if hit is None:
                continue
            if depth == len(prefixes):
                assert isinstance(hit, _Mark)
                return self._region(hit)
            # Leaf absent but a parent key is proven in this very file.
            return SourceLocation(uri=self.uri)
        return None

    def _region(self, mark: _Mark) -> SourceLocation:
        return SourceLocation(
            uri=self.uri,
            start_line=mark.line,
            start_column=mark.column,
            end_line=mark.end_line,
            end_column=mark.end_column,
        )

    def __repr__(self) -> str:
        return f"YamlSourceIndex(uri={self.uri!r}, entries={len(self._marks)})"


class _Walker:
    """Indexes marks for one composed document."""

    def __init__(self, marks: dict[str, object]) -> None:
        self._marks = marks
        self._visited: set[int] = set()
        self._aliased: set[int] = set()
        self._count = 0

    def _put(self, path: tuple[str, ...], mark: _Mark) -> None:
        key = ".".join(path)
        self._marks[key] = _AMBIGUOUS if key in self._marks else mark

    def walk(self, node: Node, path: tuple[str, ...], *, again: bool = False) -> None:
        """Index `node` under `path`.

        `again` re-walks an already indexed subtree under its semantic-name prefix; nodes
        found to be YAML aliases in the first pass stay excluded.
        """
        self._count += 1
        if self._count > _MAX_NODES:
            raise RecursionError("yaml document too large to index")
        if again:
            if id(node) in self._aliased:
                return
        elif id(node) in self._visited:
            # A node reachable twice is a YAML alias: its marks belong to the anchor site,
            # so the aliased path must never inherit them.
            self._aliased.add(id(node))
            return
        else:
            self._visited.add(id(node))
        self._children(node, path, again)

    def _children(self, node: Node, path: tuple[str, ...], again: bool) -> None:
        if isinstance(node, MappingNode):
            for key_node, value_node in node.value:
                if not isinstance(key_node, ScalarNode) or key_node.tag == _MERGE_TAG:
                    continue
                child = (*path, str(key_node.value))
                self._put(child, _key_mark(key_node))
                self.walk(value_node, child, again=again)
        elif isinstance(node, SequenceNode):
            for i, item in enumerate(node.value):
                if again:
                    if id(item) in self._aliased:
                        continue
                elif id(item) in self._visited:
                    self._aliased.add(id(item))
                    continue  # an aliased entry: its text position is not this entry's
                numeric = (*path, str(i))
                start = item.start_mark
                entry = _Mark(start.line + 1, start.column + 1, None, None)
                self._put(numeric, entry)
                name = _entry_name(item)
                alias = (*path, name) if name is not None else None
                if alias is not None:
                    self._put(alias, entry)
                self.walk(item, numeric, again=again)
                if alias is not None and self._marks.get(".".join(alias)) is not _AMBIGUOUS:
                    self._children(item, alias, True)


def _key_mark(key: ScalarNode) -> _Mark:
    start, end = key.start_mark, key.end_mark
    if end.line == start.line:
        return _Mark(start.line + 1, start.column + 1, end.line + 1, end.column + 1)
    return _Mark(start.line + 1, start.column + 1, None, None)


def _entry_name(item: Node) -> str | None:
    """The `name` scalar of a mapping list entry, used as a semantic alias."""
    if not isinstance(item, MappingNode):
        return None
    for key_node, value_node in item.value:
        if (
            isinstance(key_node, ScalarNode)
            and key_node.value == "name"
            and isinstance(value_node, ScalarNode)
            and value_node.tag == "tag:yaml.org,2002:str"
        ):
            return str(value_node.value)
    return None
