"""G-ONE-LAZY-SOURCE: the engine owns every lazy reader and every format choice (RUN-STREAM C1l).

`src/decoy/cli/io/_lazy.py` and `src/decoy/cli/run/` get lazy sources only from the engine's
`build_lazy_source`. A reader class name (`LazySource`, `FixedWidthLazySource`, `CsvLazySource`),
also through an import alias or a `decoy_engine.profile.<name>` attribute, or a format dispatch
(`==` either way, `in (...)`, `match`/`case`, a dict keyed by a format name, `.get("format")`)
would copy the engine's table, so the scan refuses both.

Named limits of a syntax walk: a class reached through `getattr` with a built name, and a format
held in a variable that is later compared.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy" / "cli"
_SCANNED = [SRC / "io" / "_lazy.py", *sorted((SRC / "run").glob("*.py"))]
_CLASSES = {"LazySource", "FixedWidthLazySource", "CsvLazySource"}
_FORMATS = {"parquet", "csv", "fixed_width"}
# Existing format checks in `run/` that are not lazy-source construction. Each is keyed by its
# stripped line text; the first two belong to the `--chunked` branch, which C2 rebuilds on the
# engine stream and removes, the third picks the format of a sample target.
_OTHER_FORMAT_LINES = {
    'partial(parquet_schema, src_path) if src_spec.get("format") == "parquet" else None',
    'if isinstance(_s, dict) and _s.get("format") == "fixed_width"',
    'if fmt == "fixed_width":',
}


def _is_format_text(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in _FORMATS


def _is_format_ref(node: ast.AST) -> bool:
    """`x["format"]`, `x.get("format")` or a name or attribute called `format` or `fmt`."""
    if isinstance(node, ast.Subscript):
        return isinstance(node.slice, ast.Constant) and node.slice.value == "format"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            node.func.attr == "get"
            and bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "format"
        )
    if isinstance(node, ast.Name):
        return node.id in {"format", "fmt"}
    return isinstance(node, ast.Attribute) and node.attr in {"format", "fmt"}


def violations(source: str, allowed: frozenset[str] | set[str] = frozenset()) -> list[int]:
    """Line numbers of an engine reader class name or a format dispatch, less allowed lines."""
    tree = ast.parse(source)
    text = source.splitlines()
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name in _CLASSES for alias in node.names):
                lines.add(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in _CLASSES:
            lines.add(node.lineno)
        elif isinstance(node, ast.Name) and node.id in _CLASSES:
            lines.add(node.lineno)
        elif isinstance(node, ast.Compare):
            parts = [node.left, *node.comparators]
            texts = [p for p in parts if _is_format_text(p)]
            tuples = [
                p
                for p in parts
                if isinstance(p, (ast.Tuple, ast.List, ast.Set))
                and any(_is_format_text(e) for e in p.elts)
            ]
            if (texts or tuples) and any(_is_format_ref(p) for p in parts):
                lines.add(node.lineno)
        elif isinstance(node, ast.Dict):
            if any(k is not None and _is_format_text(k) for k in node.keys):
                lines.add(node.lineno)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                for sub in ast.walk(case.pattern):
                    if isinstance(sub, ast.MatchValue) and _is_format_text(sub.value):
                        lines.add(case.pattern.lineno)
        elif isinstance(node, ast.Call) and _is_format_ref(node):
            lines.add(node.lineno)
    return sorted(n for n in lines if text[n - 1].strip() not in allowed)


def test_no_reader_class_or_format_dispatch_in_the_lazy_path() -> None:
    found = {
        str(path.relative_to(ROOT)): hits
        for path in _SCANNED
        if (hits := violations(path.read_text(encoding="utf-8"), _OTHER_FORMAT_LINES))
    }
    assert not found, f"the engine owns lazy readers and formats: {found}"


def test_seeded_red_cases() -> None:
    red = [
        "from decoy_engine import LazySource\n",
        "import decoy_engine.profile as p\nx = p.FixedWidthLazySource\n",
        "from decoy_engine import LazySource as L\n",
        "if d['format'] == 'csv':\n    pass\n",
        "if 'parquet' == fmt:\n    pass\n",
        "if d.get('format') in ('csv', 'parquet'):\n    pass\n",
        "match fmt:\n    case 'csv':\n        pass\n",
        "x = {'parquet': 1}\n",
        "d.get('format')\n",
    ]
    for case in red:
        assert violations(case), case
    assert not violations("kinds = classify_table_kinds(config)\nx = build_lazy_source(t, d)\n")
