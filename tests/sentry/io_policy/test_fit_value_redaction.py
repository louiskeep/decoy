"""G-FIT-REDACT: `decoy fit` writes its snapshot only through the engine's redacting writer.

`compute_distribution_snapshot` returns raw cell values (`top_values`). The file `decoy fit`
writes must come from `distribution_snapshot_document`, which withholds the values of columns the
engine's sensitivity profile flags. Two rules, both read off the syntax tree:

- no module under `src/decoy` names `compute_distribution_snapshot` in any spelling: a direct
  import, an `as` alias (the import still names the original), a module attribute
  (`snapshot.compute_distribution_snapshot`), the lazy export on `decoy_engine` or
  `decoy_engine.quality`, or a string handed to `getattr`;
- `cli/fit.py` does not re-derive sensitivity: it names neither `pii_score` nor
  `is_value_sensitive`. It reads `redacted_columns` from the document the engine built.

Named limit: a name assembled at run time (`"compute_" + "distribution_snapshot"`) is not seen.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
FIT = SRC / "cli" / "fit.py"

RAW_WRITER = "compute_distribution_snapshot"
SENSITIVITY_NAMES = frozenset({"pii_score", "is_value_sensitive"})


def named_hits(source: str, names: frozenset[str]) -> list[int]:
    """Lines where any spelling of one of `names` appears (import, name, attribute, string)."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            (isinstance(node, ast.alias) and node.name.rpartition(".")[2] in names)
            or (isinstance(node, ast.Name) and node.id in names)
            or (isinstance(node, ast.Attribute) and node.attr in names)
            or (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in names
            )
        ):
            hits.append(getattr(node, "lineno", 0))
    return hits


def test_no_module_calls_the_raw_snapshot_writer() -> None:
    found = {
        p.relative_to(SRC).as_posix(): lines
        for p in sorted(SRC.rglob("*.py"))
        if (lines := named_hits(p.read_text(encoding="utf-8"), frozenset({RAW_WRITER})))
    }
    assert not found, f"{RAW_WRITER} used in src/decoy: {found}"


def test_fit_does_not_rederive_sensitivity() -> None:
    lines = named_hits(FIT.read_text(encoding="utf-8"), SENSITIVITY_NAMES)
    assert lines == [], f"cli/fit.py re-derives sensitivity at lines {lines}"


def test_fit_reads_the_document_policy() -> None:
    assert "redacted_columns" in FIT.read_text(encoding="utf-8")


_BITE_SPELLINGS = {
    "direct import": (
        "from decoy_engine.quality.snapshot import compute_distribution_snapshot\n"
        "compute_distribution_snapshot(df)\n"
    ),
    "as alias": (
        "from decoy_engine.quality.snapshot import compute_distribution_snapshot as snap\n"
        "snap(df)\n"
    ),
    "module attribute": (
        "from decoy_engine.quality import snapshot\nsnapshot.compute_distribution_snapshot(df)\n"
    ),
    "lazy export": "import decoy_engine\ndecoy_engine.quality.compute_distribution_snapshot(df)\n",
    "getattr string": "import decoy_engine\ngetattr(decoy_engine, 'compute_distribution_snapshot')\n",
}


def test_scanner_bites_every_spelling() -> None:
    for label, source in _BITE_SPELLINGS.items():
        assert named_hits(source, frozenset({RAW_WRITER})), f"missed: {label}"


def test_scanner_bites_sensitivity_reads() -> None:
    source = (
        "from decoy_engine.profiling import is_value_sensitive\n"
        "keep = [c for c in cols if c.pii_score > 0.6]\n"
        "is_value_sensitive(c)\n"
    )
    assert len(named_hits(source, SENSITIVITY_NAMES)) == 3


def test_scanner_passes_the_engine_document_route() -> None:
    source = (
        "from decoy_engine import distribution_snapshot_document\n"
        "doc = distribution_snapshot_document(df)\ndoc['redacted_columns']\n"
    )
    assert named_hits(source, frozenset({RAW_WRITER}) | SENSITIVITY_NAMES) == []
