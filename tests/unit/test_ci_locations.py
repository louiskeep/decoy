"""A5: dotted engine/Pydantic paths -> exact YAML marks, or no guessed region.

The oracle for every expected line/column is computed by plain string search over
the same text, independently of PyYAML's marks.
"""

from __future__ import annotations

import pytest
from decoy.ci.contracts import SourceLocation
from decoy.ci.locations import YamlSourceIndex
from tests.ci_support import CLEAN_PIPELINE


def _pos(text: str, needle: str, occurrence: int = 1) -> tuple[int, int]:
    """1-based (line, column) of the Nth occurrence of `needle`, columns in code points."""
    idx = -1
    for _ in range(occurrence):
        idx = text.index(needle, idx + 1)
    before = text[:idx]
    line = before.count("\n") + 1
    col = idx - (before.rfind("\n") + 1) + 1
    return line, col


def _index(text: str, uri: str = "pipeline.yaml") -> YamlSourceIndex:
    return YamlSourceIndex.from_bytes(uri, text.encode("utf-8"))


def _assert_key(loc: SourceLocation | None, text: str, key: str, occurrence: int = 1) -> None:
    line, col = _pos(text, key, occurrence)
    assert loc is not None
    assert (loc.start_line, loc.start_column) == (line, col)
    # single-line key: the end is one-based and exclusive
    assert (loc.end_line, loc.end_column) == (line, col + len(key))


def test_block_style_exact_leaf_numeric_and_semantic_agree() -> None:
    idx = _index(CLEAN_PIPELINE)
    semantic = idx.locate("tables.customers.columns.email.provider")
    numeric = idx.locate("tables.0.columns.0.provider")
    _assert_key(semantic, CLEAN_PIPELINE, "provider")
    assert semantic == numeric
    assert semantic.uri == "pipeline.yaml"


def test_mapping_key_paths_resolve_directly() -> None:
    idx = _index(CLEAN_PIPELINE)
    _assert_key(idx.locate("sources.customers.path"), CLEAN_PIPELINE, "path")
    _assert_key(idx.locate("targets.customers.path"), CLEAN_PIPELINE, "path", occurrence=2)
    _assert_key(idx.locate("global_settings.seed"), CLEAN_PIPELINE, "seed")


def test_list_entry_alias_marks_the_entry_start_only() -> None:
    idx = _index(CLEAN_PIPELINE)
    loc = idx.locate("tables.customers.columns.email")
    line, col = _pos(CLEAN_PIPELINE, "name: email")
    assert (loc.start_line, loc.start_column) == (line, col)
    assert loc.end_line is None and loc.end_column is None
    assert idx.locate("tables.0.columns.0") == loc


def test_moving_the_key_moves_the_region() -> None:
    moved = "# a\n# b\n" + CLEAN_PIPELINE
    a = _index(CLEAN_PIPELINE).locate("tables.customers.columns.email.provider")
    b = _index(moved).locate("tables.customers.columns.email.provider")
    assert b.start_line == a.start_line + 2 and b.start_column == a.start_column


def test_flow_style_and_quoted_keys() -> None:
    text = "root: {alpha: {\"beta key\": 1, 'gamma': [10, {delta: 2}]}}\n"
    idx = _index(text)
    _assert_key(idx.locate("root.alpha"), text, "alpha")
    loc = idx.locate("root.alpha.beta key")
    line, col = _pos(text, '"beta key"')
    assert (loc.start_line, loc.start_column) == (line, col)
    _assert_key(idx.locate("root.alpha.gamma.1.delta"), text, "delta")


def test_unicode_columns_count_code_points_not_bytes() -> None:
    text = 'k\u00e9y: \u00fcber\nflow: {"\u043a\u043b\u044e\u0447": 1, target: 2}\n'
    idx = _index(text)
    _assert_key(idx.locate("flow.target"), text, "target")
    _assert_key(idx.locate("k\u00e9y"), text, "k\u00e9y")


def test_crlf_line_endings_keep_one_based_lines() -> None:
    text = CLEAN_PIPELINE.replace("\n", "\r\n")
    loc = _index(text).locate("tables.customers.columns.email.provider")
    line, col = _pos(CLEAN_PIPELINE, "provider")
    assert (loc.start_line, loc.start_column) == (line, col)


def test_nearest_proved_parent_is_file_level_without_a_region() -> None:
    idx = _index(CLEAN_PIPELINE)
    loc = idx.locate("tables.customers.columns.email.cardinality_mode")
    assert loc == SourceLocation(uri="pipeline.yaml")
    assert loc.start_line is None


def test_bracket_notation_from_engine_paths_is_normalized() -> None:
    text = "nodes:\n  - id: a\n  - id: b\n    config:\n      path: x\n"
    idx = _index(text)
    _assert_key(idx.locate("nodes[1].config.path"), text, "path")


@pytest.mark.parametrize(
    "path",
    [
        None,
        "",
        "tables.*.columns",
        "tables.customers.columns.*.provider",
        "<snapshot_file=anything>",
        "tables.<unknown>.x",
        "totally.absent.path",
    ],
)
def test_wildcards_pseudo_paths_and_unknowns_produce_no_region(path) -> None:
    assert _index(CLEAN_PIPELINE).locate(path) is None


def test_duplicate_names_are_ambiguous_but_indexes_still_resolve() -> None:
    text = (
        "tables:\n"
        "  - name: dup\n"
        "    columns:\n"
        "      - name: a\n"
        "        provider: x\n"
        "  - name: dup\n"
        "    columns:\n"
        "      - name: a\n"
        "        provider: y\n"
    )
    idx = _index(text)
    assert idx.locate("tables.dup.columns.a.provider") is None
    assert idx.locate("tables.dup") is None
    _assert_key(idx.locate("tables.1.columns.0.provider"), text, "provider", occurrence=2)


def test_duplicate_mapping_keys_are_ambiguous() -> None:
    text = "a:\n  b: 1\na:\n  b: 2\n"
    assert _index(text).locate("a.b") is None


def test_alias_numeric_collision_is_ambiguous() -> None:
    text = 'items:\n  - name: "1"\n    v: 1\n  - name: two\n    v: 2\n'
    idx = _index(text)
    assert idx.locate("items.1") is None  # numeric 1 vs the entry NAMED "1"
    assert idx.locate("items.two") is not None


def test_yaml_aliases_never_yield_the_anchor_site_for_the_alias_path() -> None:
    text = "base: &b\n  provider: person_email\nuse: *b\n"
    idx = _index(text)
    _assert_key(idx.locate("base.provider"), text, "provider")
    loc = idx.locate("use.provider")
    # either no region or file-level; never the anchor's line
    assert loc is None or loc.start_line is None
    use = idx.locate("use")
    line, _ = _pos(text, "use")
    assert use is not None and use.start_line == line


def test_merge_key_children_have_no_guessed_region() -> None:
    text = "base: &b {provider: p}\nchild:\n  <<: *b\n  other: 1\n"
    loc = _index(text).locate("child.provider")
    assert loc is None or loc.start_line is None


def test_malformed_yaml_has_an_empty_index() -> None:
    idx = _index("a: [unterminated\n  b: : :\n")
    assert idx.locate("a") is None


def test_non_utf8_bytes_have_an_empty_index() -> None:
    assert YamlSourceIndex.from_bytes("p.yaml", b"\xff\xfe\x00bad").locate("a") is None


def test_uri_is_taken_from_the_caller_not_derived() -> None:
    assert _index("a: 1\n", "sub/dir/p.yaml").locate("a").uri == "sub/dir/p.yaml"


def test_index_holds_marks_and_path_tokens_only() -> None:
    canary = "SCALAR_VALUE_CANARY_c19f02"
    idx = _index(f"a:\n  b: {canary}\n")
    assert canary not in repr(idx) and canary not in repr(vars(idx))
