"""Every committed baseline or allowlist a CLI sentry reads is registered and mirrored.

The ratchet only protects what ``sentry_registry.toml`` names. This test ties each live source
to its registered baseline (same key set, both directions) and fails when any file in the
``SENTRIES`` manifest (``tests/unit`` sentries included) holds an allowlist-shaped constant or
reads a committed list that is not registered, so a new allowlist cannot sit beside the ratchet.

Ported from decoy-engine ``tests/sentry/test_baseline_registry.py`` (X0a).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _baseline_sources as bs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

LIST_NAME = re.compile(r"ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS")
DATA_LITERAL = re.compile(r"[\w.\-]+\.(?:json|toml)$")
SENTRIES: tuple[str, ...] = bs.load_module(bs.SENTRY / "test_sentry_manifest.py").SENTRIES


def registry() -> dict[str, str]:
    text = bs.REGISTRY.read_text(encoding="utf-8")
    return {r["id"]: r["baseline"] for r in tomllib.loads(text).get("sentry", [])}


@pytest.mark.parametrize("src", bs.SOURCES, ids=lambda s: s.sentry_id)
def test_source_matches_its_registered_baseline(src: bs.Source) -> None:
    rel = registry().get(src.sentry_id)
    assert rel == f"tests/sentry/baselines/{src.sentry_id}.json", "sentry not registered"
    doc = json.loads((bs.ROOT / rel).read_text(encoding="utf-8"))
    assert doc["sentry_id"] == src.sentry_id
    live, recorded = src.keys(), set(doc["entries"])
    assert live - recorded == set(), "live entries missing from the baseline"
    assert recorded - live == set(), "stale baseline entries (shrink the baseline)"


def test_registry_has_no_source_less_sentry() -> None:
    assert set(registry()) == {s.sentry_id for s in bs.SOURCES}


def unregistered_readers(
    sources: dict[str, str],
    data_files: set[str],
    covered_consts: set[tuple[str, str]],
    covered_files: set[str],
) -> list[str]:
    """Allowlist-shaped module constants and committed data files read but not registered."""
    found = []
    for name, text in sources.items():
        tree = ast.parse(text)
        for node in tree.body:
            targets = (
                node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            )
            for t in targets:
                is_list = isinstance(t, ast.Name) and LIST_NAME.search(t.id)
                is_coll = isinstance(
                    getattr(node, "value", None), (ast.Dict, ast.Tuple, ast.List, ast.Set)
                )
                if is_list and is_coll and (name, t.id) not in covered_consts:
                    found.append(f"{name}: constant {t.id}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                base = node.value.rsplit("/", 1)[-1]
                if (
                    DATA_LITERAL.fullmatch(base)
                    and base in data_files
                    and base not in covered_files
                ):
                    found.append(f"{name}: data file {base}")
    return sorted(set(found))


def _covered() -> tuple[set[tuple[str, str]], set[str]]:
    consts = {(s.keys.test_file, s.keys.constant) for s in bs.SOURCES} | set(bs.NOT_A_LIST_CONSTS)
    files = {Path(p).name for p in registry().values()}
    return consts, files


def _data_files() -> set[str]:
    return {
        p.name
        for root in ("tests", "docs")
        for p in (bs.ROOT / root).rglob("*")
        if p.suffix in {".json", ".toml"}
    }


def _manifest_sources() -> dict[str, str]:
    # Keyed by basename, as NOT_A_LIST_CONSTS and InCode are; the names must not collide.
    names = [Path(s).name for s in SENTRIES]
    assert len(set(names)) == len(names), "two manifest files share a basename"
    out = {Path(s).name: (bs.ROOT / s).read_text(encoding="utf-8") for s in SENTRIES}
    out.pop("test_baseline_registry.py")  # holds the seeded fixtures below
    return out


def test_no_sentry_reads_an_unregistered_baseline() -> None:
    consts, files = _covered()
    assert unregistered_readers(_manifest_sources(), _data_files(), consts, files) == []


def test_not_a_list_consts_still_exist() -> None:
    sources = _manifest_sources()
    stale = [
        f"{f}: {c}"
        for f, c in bs.NOT_A_LIST_CONSTS
        if not re.search(rf"^{c}\b", sources.get(f, ""), re.MULTILINE)
    ]
    assert stale == []


def test_seeded_unregistered_readers_are_caught() -> None:
    consts, files = _covered()
    seeded_const = {"test_new.py": 'NEW_ALLOWLIST = {"a": "b"}\n'}
    assert unregistered_readers(seeded_const, set(), consts, files) == [
        "test_new.py: constant NEW_ALLOWLIST"
    ]
    seeded_file = {"test_new.py": 'P = ROOT / "tests" / "fixtures" / "fresh-list.json"\n'}
    assert unregistered_readers(seeded_file, {"fresh-list.json"}, consts, files) == [
        "test_new.py: data file fresh-list.json"
    ]
